#!/usr/bin/env python3

"""An interactive viewer for todo-txt."""

import os
import re
import sys
import argparse
import subprocess
import curses

"""Maps a priority to a color. First entry is priority A, second B, and so on.
If there are more priorities than colors, the last entry will be used for the
remainder.
"""
COLORS = [
    '#F5D761',
    '#A4F54C',
    '#78C1F3',
    '#837CC5',
    '#CCCCCC'
]
COLOR_STATUSBAR = '#AAAAAA'
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


def is_context_or_project(word):
    """Returns True if the word is a @context or +project, False otherwise."""
    return word.startswith('@') or word.startswith('+')


def get_num_rows():
    """Returns the number of lines currently available in the terminal."""
    # pylint: disable=E1101
    return curses.LINES - 1


def get_num_columns():
    """Returns the columns of lines currently available in the terminal."""
    # pylint: disable=E1101
    return curses.COLS


class Dialog:
    """A popup dialog that lets us interact with todo items."""

    def __init__(self, item):
        self.dialog = None
        self.alive = True
        self.item = item

    def run(self):
        """Shows the dialog and enters a rendering loop."""
        self._init()
        while self.alive:
            self._render()
            self._handle_input()

    def close(self):
        """Closes the dialog."""
        self.alive = False

    def _init(self):
        self.dialog = curses.newwin(5, get_num_columns(), 0, 0)

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
        return self.items and self.selected_line >= 0

    @property
    def selected_item(self):
        """Returns the currently selected item, which is a tuple in the form of:
        (item_id, line), item_id being the line number in the todo.txt and line
        being the text of that line.
        """
        return self.items[self.selected_line] if self.items else None

    @property
    def selected_id(self):
        item = self.selected_item
        return item[0] if item else None

    def __init__(self, root, simple_colors=False):
        self.root = root
        self.screen = None
        self.scroll_offset = 0
        self.selected_line = 0
        self.alive = True
        self.items = []
        self.all_items = []
        self.filter = ''
        self.filtering = False
        self.simple_colors = simple_colors
        self.num_colors = 0
        self.num_reserved_colors = 0
        self.num_color_variants = 0

    def run(self, *_):
        """Shows the viewer and enters a rendering loop."""
        try:
            self._init()
            while self.alive:
                self._move_selection_into_view()
                self._render()
                if self.filtering:
                    self._handle_filter_input()
                else:
                    self._handle_input()
        except KeyboardInterrupt:
            pass

    def close(self):
        """Closes the viewer."""
        self.alive = False

    def select_item(self, item_id):
        """Selects the item with a specific id."""
        for item_index, item in enumerate(self.items):
            if item[0] == item_id:
                self.selected_line = item_index
                break

    def _run_subprocess(self, command):
        curses.endwin()
        subprocess.run([str(x) for x in command])
        self._init()

    def _init(self):
        self._read_todo_file()
        self.screen = curses.initscr()
        self.screen.keypad(1)
        self.screen.border(0)
        curses.noecho()
        curses.curs_set(0)
        # curses.mousemask(1)
        curses.start_color()
        if not curses.can_change_color():
            self.simple_colors = True
        if not self.simple_colors:
            # Set reserved colors
            self._define_color(1, hex_to_rgb(COLOR_STATUSBAR))
            self._define_color(2, hex_to_rgb(COLOR_STATUSBAR_ACTIVE))
            self.num_reserved_colors = 3
            # Set item colors
            self.num_color_variants = 3
            for color_index, color in enumerate(COLORS):
                color_index = color_index * self.num_color_variants + self.num_reserved_colors
                self._define_color(color_index, hex_to_rgb(color))
                self._define_color(color_index + 1, dim(hex_to_rgb(color)))
                self._define_color(color_index + 2, lighten(hex_to_rgb(color)))
            self.num_colors = len(COLORS)
        else:
            # Set reserved colors
            curses.init_pair(1, 0, COLOR_STATUSBAR_FALLBACK)
            curses.init_pair(2, 0, COLOR_STATUSBAR_ACTIVE_FALLBACK)
            self.num_reserved_colors = 3
            # Set item colors
            self.num_color_variants = 1
            for color_index, color in enumerate(COLORS_FALLBACK):
                color_index += self.num_reserved_colors
                curses.init_pair(color_index, color, 0)
            self.num_colors = len(COLORS_FALLBACK)

    def _define_color(self, color_index, rgb):
        assert color_index > 0  # Don't overwrite background color
        curses.init_color(color_index, *rgb)
        curses.init_pair(color_index, color_index, 0)

    def _get_item_color_index(self, item):
        priority = get_priority_as_number(item, maximum=self.num_colors - 1)
        return priority * self.num_color_variants + self.num_reserved_colors

    def _get_item_color_variants(self, item):
        color_index = self._get_item_color_index(item)
        pair = curses.color_pair
        if self.simple_colors:
            return (
                pair(color_index),
                pair(color_index) | curses.A_DIM,
                pair(color_index) | curses.A_BOLD)
        else:
            return (
                pair(color_index),
                pair(color_index if self.simple_colors else color_index + 1),
                pair(color_index if self.simple_colors else color_index + 2)
            )

    def _read_todo_file(self):
        self.items.clear()
        with open(os.path.join(self.root, 'todo.txt'), 'r') as todofile:
            lines = todofile.readlines()
        items = [(index + 1, line) for index, line in enumerate(lines)]
        self.all_items = sorted(items, key=get_priority_as_number)
        self.items = self.all_items
        self._apply_filter()

    def _apply_filter(self):
        if not self.filter:
            self.items = self.all_items
        else:
            self.items = []
            for item in self.all_items:
                if self.filter.lower() in item[1].lower():
                    self.items.append(item)
        self.selected_line = 0

    def _handle_filter_input(self):
        key = self.screen.getch()
        if key in (ord('\n'), curses.KEY_UP, curses.KEY_DOWN, KEY_ESC):
            self.filtering = False
        elif key == KEY_BACKSPACE:
            self.filter = self.filter[:len(
                self.filter) - 1] if self.filter else ''
        else:
            self.filter += chr(key)
        self._apply_filter()

    def _handle_input(self):
        key = self.screen.getch()
        # j/k: up/down
        if key in (ord('k'), curses.KEY_UP):
            self.selected_line -= 1
        elif key in (ord('j'), curses.KEY_DOWN):
            self.selected_line += 1
        # HOME/END: scroll to top/bottom
        elif key == curses.KEY_HOME:
            self.selected_line = 0
        elif key == curses.KEY_END:
            self.selected_line = len(self.items) - 1
        # q/ESC: cancel filter or quit
        elif key in (ord('q'), KEY_ESC):
            if self.filter:
                selected = self.selected_id
                self.filter = ''
                self._apply_filter()
                self.select_item(selected)
            else:
                self.close()
        # r: refresh
        elif key == ord('r'):
            self._read_todo_file()
            curses.flash()
        # e: edit
        elif key == ord('e'):
            self._run_subprocess(['todo.sh', 'edit'])
        # /: filter
        elif key == ord('/'):
            self.filter = ''
            self.filtering = True
        # d: done
        elif self.has_selection and key == ord('d'):
            self._run_subprocess(['todo.sh', 'do', self.selected_id])
        # n: nav
        elif self.has_selection and key == ord('n'):
            self._run_subprocess(['todo.sh', 'nav', self.selected_id])
        # SPACE/RETURN: Enter item dialog
        elif self.has_selection and key in (ord(' '), ord('\n')):
            Dialog(self.selected_item).run()
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
            self._run_subprocess(['todo.sh', 'depri', self.selected_id])
        # Mouse events
        # elif key == curses.KEY_MOUSE:
        #     _, _, row, _, _ = curses.getmouse()
        #     self.selected_line = row

    def _set_item_priority(self, item, priority):
        self._run_subprocess(['todo.sh', 'pri', item[0], priority])
        self.select_item(item[0])

    def _move_selection_into_view(self):
        num_rows = get_num_rows() - 1  # Leave one row for the status bar
        self.selected_line = max(
            0, min(len(self.items) - 1, self.selected_line))
        if self.selected_line < self.scroll_offset:
            self.scroll_offset = self.selected_line
        elif self.selected_line > num_rows + self.scroll_offset:
            self.scroll_offset = self.selected_line - num_rows

    def _print(self, row, col, chunks):
        for text, attr in chunks:
            num_chars = len(text)
            if col + num_chars > get_num_columns():
                num_chars = get_num_columns() - col
                if num_chars <= 0:
                    break  # No space left in the row
            self.screen.addnstr(row, col, text, num_chars, attr)
            col += num_chars

    def _print_item(self, index, item, selected=False):
        color, color_dim, color_light = self._get_item_color_variants(item)
        standout = curses.A_STANDOUT if selected else 0
        linenum, line = item
        line = re.sub(RE_PRIORITY + ' ', '', line)  # Hide priorities
        line = re.sub(RE_DATE + ' ', '', line)  # Hide dates
        self._print(index, 0, [
            ('{:02d} '.format(linenum), color_dim | standout),
            *map(lambda word: (word + ' ',
                               (color_light if is_context_or_project(word) else color) | standout), line.split())
        ])

    def _render_statusbar(self):
        top = self.scroll_offset + 1
        bottom = min(len(self.items), self.scroll_offset + get_num_rows())
        total = len(self.all_items)
        text = 'FILTERING: {:}'.format(
            self.filter) if self.filter or self.filtering else ''
        attr = curses.color_pair(2 if self.filtering else 1)
        text = 'Showing {:}-{:}/{:} {:}'.format(top, bottom, total, text)
        self.screen.addnstr(get_num_rows(), 0, text.ljust(get_num_columns() - 1),
                            get_num_columns(), attr)

    def _render(self):
        self.screen.erase()
        top = self.scroll_offset
        bottom = self.scroll_offset + get_num_rows()
        for index, item in enumerate(self.items[top:bottom]):
            self._print_item(index, item)
        if self.items:
            self._print_item(self.selected_line - self.scroll_offset,
                             self.items[self.selected_line], True)
        self._render_statusbar()
        self.screen.refresh()


def main():
    """Main entry point. Parses command line arguments and runs the viewer."""
    parser = argparse.ArgumentParser()
    parser.add_argument("dir")
    parser.add_argument('--simple', dest='simple_colors', action='store_true',
                        help='use simple colors for terminals that do not ' +
                        'support defining colors in RGB')
    parser.set_defaults(simple=False)
    args = parser.parse_args()
    curses.wrapper(TodoListViewer(
        args.dir, simple_colors=args.simple_colors).run)


if __name__ == '__main__':
    main()
