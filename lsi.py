#!/usr/bin/env python3

"""An interactive viewer for todo-txt."""

import os
import re
import sys
import time
import argparse
import subprocess
import curses
from contextlib import contextmanager, suppress

"""Maps a priority to a color. First entry is priority A, second B, and so on.
If there are more priorities than colors, the last entry will be used for the
remainder.
"""
COLORS = [
    '#FF7733',
    '#F5D761',
    '#A4F54C',
    '#78C1F3',
    '#837CC5',
    '#CCCCCC'
]
COLOR_STATUSBAR = '#CCCCCC'
COLOR_STATUSBAR_ACTIVE = '#F5D761'

"""For terminals that don't support definining custom colors (which is most of
them), these pre-defined colors will be used instead."""
COLORS_FALLBACK = [
    curses.COLOR_RED,
    curses.COLOR_YELLOW,
    curses.COLOR_GREEN,
    curses.COLOR_CYAN,
    curses.COLOR_BLUE,
    curses.COLOR_MAGENTA,
    curses.COLOR_WHITE
]
COLOR_STATUSBAR_FALLBACK = curses.COLOR_WHITE
COLOR_STATUSBAR_ACTIVE_FALLBACK = curses.COLOR_YELLOW

RE_PRIORITY = r'\(([A-Z])\)'
RE_DATE = r'\d{4}-\d{2}-\d{2}'
KEY_ESC = 27
KEY_BACKSPACE = 127


def get_priority(item):
    """Returns the priority of an item as a letter."""
    match = re.search(RE_PRIORITY, item[1])
    return match.group(1) if match else None


def get_priority_as_number(item, maximum=sys.maxsize):
    """Returns the priority of an item as a number (A is 0, B is 1, ...)."""
    priority = get_priority(item)
    if priority is None:
        return maximum
    return min(maximum, ord(priority) - ord('A'))


def get_bumped_priority(item, delta):
    """Offsets and returns an item's priority by delta (positive -> higher)."""
    priority = get_priority(item)
    return chr(max(ord('A'), min(ord('Z'), ord(priority) - delta)))


def hex_to_rgb(col):
    """Extracts the RGB values as integers (from 0 to 1000) from a hex color
    string (#rrggbb).
    """
    mul = 1000 / 255
    return tuple(round(int(col.lstrip('#')[i:i + 2], 16) * mul) for i in (0, 2, 4))


def dim(rgb, mul=0.6):
    """Returns a dimmer version of a color. If multiplier > 1, a lighter color
    can be produced as well."""
    return tuple(map(lambda x: min(1000, round(x * mul)), rgb))


def lighten(rgb, mul=1.5):
    """An alias for dim() with a positive multiplier."""
    return dim(rgb, mul)


class Dialog:
    """A popup dialog that lets us interact with todo items."""

    def __init__(self, screen, item):
        self.item = item
        self.parent = screen
        self.dialog = None
        self._alive = True

    def run(self):
        """Shows the dialog and enters a rendering loop."""
        self._init()
        while self._alive:
            self._render()
            self._handle_input()

    def close(self):
        """Closes the dialog."""
        self._alive = False

    def _init(self):
        _, num_cols = self.parent.getmaxyx()
        self.dialog = curses.newwin(5, num_cols, 0, 0)

    def _handle_input(self):
        self.dialog.getch()
        self.close()

    def _render(self):
        self.dialog.erase()
        self.dialog.attron(curses.color_pair(0))
        self.dialog.addstr(1, 2, '{:} {:}'.format(*self.item))
        self.dialog.box()
        self.dialog.refresh()


class TodoListViewer:
    """A viewer that lets us browse and filter todo items."""

    @property
    def has_selection(self):
        """Returns True if a todo item is selected, False otherwise."""
        return self._items and self._selected_line >= 0

    @property
    def selected_item(self):
        """Returns the currently selected item, which is a tuple in the form of:
        (item_id, line), item_id being the line number in the todo.txt and line
        being the text of that line.
        """
        return self._items[self._selected_line] if self._items else None

    @property
    def selected_id(self):
        """Returns the line number of the currently selected item."""
        item = self.selected_item
        return item[0] if item else None

    @property
    def todo_path(self):
        """Returns the absolute path to the user's todo.txt."""
        return os.path.abspath(os.path.join(self._root, 'todo.txt'))

    @property
    def num_rows(self):
        """Number of terminal lines available."""
        return self.screen.getmaxyx()[0] - 1

    @property
    def num_columns(self):
        """Number of terminal characters available horizontally."""
        return self.screen.getmaxyx()[1]

    @property
    def is_watching(self):
        """Returns True if the viewer will respond to changes in todo.txt."""
        return self._observer is not None and self._watch

    # pylint: disable=W0622
    def __init__(self, root, filter=None, simple_colors=False, mouse=False,
                 watch=True):
        self.screen = None
        self._root = root
        self._scroll_offset = 0
        self._selected_line = 0
        self._alive = True
        self._items = []
        self._all_items = []
        self._filter = filter or ''
        self._filtering = False
        self._simple_colors = simple_colors
        self._num_colors = 0
        self._num_reserved_colors = 0
        self._num_color_variants = 0
        self._mouse = mouse
        self._watch = watch
        self._observer = None

    def __del__(self):
        if self._observer:
            self._observer.stop()

    def run(self, *_):
        """Shows the viewer and enters a rendering loop."""
        try:
            self._init()
            while self._alive:
                self._move_selection_into_view()
                self._render()
                if self._filtering:
                    self._handle_filter_input()
                else:
                    self._handle_input()
        except KeyboardInterrupt:
            pass

    def close(self):
        """Closes the viewer."""
        self._alive = False

    def refresh(self):
        """Reads the todo items from filesystem and refreshes the view."""
        with self.retain_selection():
            self._read_todo_file()
            curses.flash()
        self._render()

    def select_item_id(self, item_id):
        """Selects the item with a specific id."""
        for item_index, item in enumerate(self._items):
            if item[0] == item_id:
                self._selected_line = item_index
                break

    @contextmanager
    def retain_selection(self):
        """On entering the context, saves the currently selected item and
        makes sure it is selected when the exiting the context."""
        selected = self.selected_id
        yield
        self.select_item_id(selected)

    @contextmanager
    def disable_watch(self):
        """Don't watch for filesystem changes while in this context."""
        prev = self._watch
        self._watch = False
        yield
        self._watch = prev

    def _run_subprocess(self, command, retain_selection=True):
        with self.disable_watch():
            curses.endwin()
            if retain_selection:
                with self.retain_selection():
                    subprocess.run([str(x) for x in command])
                    self._init()
            else:
                subprocess.run([str(x) for x in command])
                self._init()

    def _init(self):
        self._read_todo_file()
        self.screen = curses.initscr()
        self.screen.keypad(1)
        curses.curs_set(0)
        if self._mouse:
            curses.mousemask(1)
        self._init_colors()
        if self._watch:
            self._init_watch()

    def _init_colors(self):
        curses.start_color()
        if not curses.can_change_color():
            self._simple_colors = True
        if not self._simple_colors:
            # Set reserved colors
            self._define_color(1, hex_to_rgb(COLOR_STATUSBAR))
            self._define_color(2, hex_to_rgb(COLOR_STATUSBAR_ACTIVE))
            self._num_reserved_colors = 3
            # Set item colors
            self._num_color_variants = 3
            for color_index, color in enumerate(COLORS):
                color_index = color_index * self._num_color_variants + self._num_reserved_colors
                self._define_color(color_index, hex_to_rgb(color))
                self._define_color(color_index + 1, dim(hex_to_rgb(color)))
                self._define_color(color_index + 2, lighten(hex_to_rgb(color)))
            self._num_colors = len(COLORS)
        else:
            # Set reserved colors
            curses.init_pair(1, 0, COLOR_STATUSBAR_FALLBACK)
            curses.init_pair(2, 0, COLOR_STATUSBAR_ACTIVE_FALLBACK)
            self._num_reserved_colors = 3
            # Set item colors
            self._num_color_variants = 1
            for color_index, color in enumerate(COLORS_FALLBACK):
                color_index += self._num_reserved_colors
                curses.init_pair(color_index, color, 0)
            self._num_colors = len(COLORS_FALLBACK)

    def _init_watch(self):
        if self._observer:
            return
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
        viewer = self

        class _Watch(FileSystemEventHandler):
            def on_modified(self, event):
                if viewer.is_watching and event.src_path.endswith('todo.txt'):
                    # It appears todotxt adds the priority in a second I/O,
                    # so if we're responding too quickly there's a chance we
                    # will miss it entirely.
                    time.sleep(.1)
                    viewer.refresh()

        self._observer = Observer()
        self._observer.schedule(_Watch(), self._root)
        self._observer.start()

    def _define_color(self, color_index, rgb):
        assert color_index > 0  # Don't overwrite background color
        curses.init_color(color_index, *rgb)
        curses.init_pair(color_index, color_index, 0)

    def _get_item_color_index(self, item):
        priority = get_priority_as_number(item, maximum=self._num_colors - 1)
        return priority * self._num_color_variants + self._num_reserved_colors

    def _get_item_color_variants(self, item):
        color_index = self._get_item_color_index(item)
        pair = curses.color_pair
        if self._simple_colors:
            return (
                pair(color_index),
                pair(color_index) | curses.A_DIM,
                pair(color_index) | curses.A_BOLD)
        else:
            return (
                pair(color_index),
                pair(color_index if self._simple_colors else color_index + 1),
                pair(color_index if self._simple_colors else color_index + 2)
            )

    def _read_todo_file(self):
        self._items.clear()
        with open(self.todo_path, 'r') as todofile:
            lines = todofile.readlines()
        items = [(index + 1, line) for index, line in enumerate(lines)]
        self._all_items = sorted(items, key=get_priority_as_number)
        self._items = self._all_items
        self._apply_filter()

    def _apply_filter(self):
        if not self._filter:
            self._items = self._all_items
        else:
            self._items = []
            for item in self._all_items:
                if self._filter.lower() in item[1].lower():
                    self._items.append(item)
        self._selected_line = 0

    def _handle_filter_input(self):
        key = self.screen.getch()
        if key in (ord('\n'), curses.KEY_UP, curses.KEY_DOWN, KEY_ESC):
            self._filtering = False
        elif key == KEY_BACKSPACE:
            self._filter = self._filter[:len(
                self._filter) - 1] if self._filter else ''
        else:
            self._filter += chr(key)
        self._apply_filter()

    def _handle_input(self):
        key = self.screen.getch()
        # j/k: up/down
        if key in (ord('k'), curses.KEY_UP):
            self._selected_line -= 1
        elif key in (ord('j'), curses.KEY_DOWN):
            self._selected_line += 1
        # HOME/END: scroll to top/bottom
        elif key == curses.KEY_HOME:
            self._selected_line = 0
        elif key == curses.KEY_END:
            self._selected_line = len(self._items) - 1
        # q/ESC: cancel filter or quit
        elif key in (ord('q'), KEY_ESC):
            if self._filter:
                with self.retain_selection():
                    self._filter = ''
                    self._apply_filter()
            else:
                self.close()
        # r: refresh
        elif key == ord('r'):
            self.refresh()
        # e: edit
        elif key == ord('e'):
            self._run_subprocess(['todo.sh', 'edit'])
        # /: filter
        elif key == ord('/'):
            self._filter = ''
            self._filtering = True
        # d: done
        elif self.has_selection and key == ord('d'):
            self._run_subprocess(
                ['todo.sh', 'do', self.selected_id], retain_selection=False)
        # n: nav
        elif self.has_selection and key == ord('n'):
            self._run_subprocess(['todo.sh', 'nav', self.selected_id])
        # SPACE/RETURN: Enter item dialog
        elif self.has_selection and key in (ord(' '), ord('\n')):
            Dialog(self.screen, self.selected_item).run()
        # -/=: Bump priority
        elif self.has_selection and key in (ord('='), ord('-')):
            delta = 1 if key == ord('=') else -1
            new_priority = get_bumped_priority(self.selected_item, delta)
            self._set_item_priority(self.selected_item, new_priority)
        # A-Z: Set priority
        elif self.has_selection and key >= ord('A') and key <= ord('Z'):
            self._set_item_priority(self.selected_item, chr(key))
        # 0: Remove priority
        elif self.has_selection and key == ord('0'):
            self._set_item_priority(self.selected_item, None)
        # Mouse events
        elif key == curses.KEY_MOUSE:
            # Note: mouse support in curses seems to be pretty poor. I left this
            # code in case someone wants to experiment with it.
            _, _, row, _, state = curses.getmouse()
            if state & 0x80000:  # Wheel down
                self._selected_line -= 1
            elif state & 0x8000000:  # Wheel up
                self._selected_line += 1
            else:
                self._selected_line = row
        # Resize events
        elif key == curses.KEY_RESIZE:
            curses.resizeterm(*self.screen.getmaxyx())

    def _set_item_priority(self, item, priority):
        if priority is None:
            self._run_subprocess(['todo.sh', 'depri', item[0]])
        else:
            self._run_subprocess(['todo.sh', 'pri', item[0], priority])

    def _move_selection_into_view(self):
        num_rows = self.num_rows - 1  # Leave one row for the status bar
        self._selected_line = max(
            0, min(len(self._items) - 1, self._selected_line))
        if self._selected_line < self._scroll_offset:
            self._scroll_offset = self._selected_line
        elif self._selected_line > num_rows + self._scroll_offset:
            self._scroll_offset = self._selected_line - num_rows

    def _print(self, row, col, text, attr):
        num_chars = len(text)
        if col + num_chars > self.num_columns:
            num_chars = self.num_columns - col
        if num_chars > 0:
            with suppress(curses.error):
                self.screen.addnstr(row, col, text, num_chars, attr)
        return num_chars

    def _print_chunks(self, row, col, chunks):
        for text, attr in chunks:
            col += self._print(row, col, text, attr)

    def _get_color_for_word(self, item, word):
        color, color_dim, color_light = self._get_item_color_variants(item)
        if word.startswith('@') or word.startswith('+'):
            return color_light
        if word.startswith('http://') or word.startswith('https://'):
            return color_dim
        return color

    def _print_item(self, index, item, selected=False):
        _, color_dim, _ = self._get_item_color_variants(item)
        standout = curses.A_STANDOUT if selected else 0
        linenum, line = item
        line = re.sub(RE_PRIORITY + ' ', '', line)  # Hide priorities
        line = re.sub(RE_DATE + ' ', '', line)  # Hide dates
        self._print_chunks(index, 0, [
            ('{:02d} '.format(linenum), color_dim | standout),
            *map(lambda word: (word + ' ',
                               self._get_color_for_word(item, word) | standout), line.split())
        ])

    def _render_statusbar(self):
        top = self._scroll_offset + 1
        bottom = min(len(self._items), self._scroll_offset + self.num_rows)
        total = len(self._all_items)
        text = 'FILTERING: {:}'.format(
            self._filter) if self._filter or self._filtering else ''
        attr = curses.color_pair(
            2 if self._filtering else 1) | curses.A_STANDOUT
        text = 'Showing {:}-{:}/{:} {:}'.format(top, bottom, total, text)
        self._print(self.num_rows, 0, text.ljust(self.num_columns), attr)

    def _render(self):
        self.screen.erase()
        top = self._scroll_offset
        bottom = self._scroll_offset + self.num_rows
        for index, item in enumerate(self._items[top:bottom]):
            self._print_item(index, item, self.selected_id == item[0])
        self._render_statusbar()
        self.screen.refresh()


def main():
    """Main entry point. Parses command line arguments and runs the viewer."""
    parser = argparse.ArgumentParser()
    parser.add_argument('dir')
    parser.add_argument('filter', nargs='?', default=None)
    parser.add_argument('-s', '--simple', action='store_true',
                        help='use simple colors for terminals that do not ' +
                        'support defining colors in RGB')
    parser.add_argument('-m', '--mouse', action='store_true',
                        help='enables mouse support')
    parser.add_argument('-w', '--watch', action='store_true',
                        help='watches todo.txt for changes')
    parser.set_defaults(simple=False, mouse=False, watch=False)
    args = parser.parse_args()
    viewer = TodoListViewer(args.dir, filter=args.filter,
                            simple_colors=args.simple, mouse=args.mouse,
                            watch=args.watch)
    curses.wrapper(viewer.run)


if __name__ == '__main__':
    main()
