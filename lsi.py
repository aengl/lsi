#!/usr/bin/env python3

"""An interactive viewer for todo-txt."""

import os
import re
import sys
import argparse
import curses
import subprocess

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

"""For terminals that don't support definining custom colors (which is most of
them), these pre-defined colors will be used instead."""
COLORS_FALLBACK = [
    3,  # yellow
    2,  # green
    6,  # cyan
    4,  # blue
    7,  # white
]

RE_PRIORITY = r'\(([A-Z])\)'
RE_CONTEXT_OR_PROJECT = r'([@+][^\s]+)'
KEY_ESC = 27


def get_priority(item):
    """Returns the priority of an item as a letter."""
    match = re.search(RE_PRIORITY, item[1])
    return match and match.group(1) or None


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


def get_num_lines():
    """Returns the number of lines currently available in the terminal."""
    # pylint: disable=E1101
    return curses.LINES - 2


def get_num_columns():
    """Returns the columns of lines currently available in the terminal."""
    # pylint: disable=E1101
    return curses.COLS


class Dialog:
    """A popup dialog that lets us interact with todo items."""

    def __init__(self, item):
        self.dialog = None
        self.close = False
        self.item = item
        self.actions = []

    def run(self):
        """Shows the dialog and enters a rendering loop."""
        self._init()
        while not self.close:
            self._render()
            self._handle_input()

    def _init(self):
        self.dialog = curses.newwin(10, get_num_columns(), 0, 0)
        self.actions = ['do', 'nav']

    def _handle_input(self):
        key = self.dialog.getch()
        if key in (ord('k'), KEY_UP):
            self._navigate(-1)
        elif key in (ord('j'), KEY_DOWN):
            self._navigate(1)
        elif key in (ord('q'), KEY_ESC):
            self.close = True

    def _navigate(self, delta):
        pass

    def _render(self):
        self.dialog.erase()
        self.dialog.addstr(1, 2, '{:} {:}'.format(*self.item))
        for action_index, action in enumerate(self.actions):
            self.dialog.addstr(action_index + 3, 2, action)
        self.dialog.box()
        self.dialog.refresh()


class TodoListViewer:
    """A viewer that lets us browse and filter todo items."""

    @property
    def selected_item(self):
        """Returns the currently selected item, which is a tuple in the form of:
        (item_id, line), item_id being the line number in the todo.txt and line
        being the text of that line.
        """
        return self.items[self.selected_line]

    def __init__(self, root):
        self.root = root
        self.screen = None
        self.scroll_offset = 0
        self.selected_line = 0
        self.close = False
        self.items = []
        self.num_colors = 0

    def run(self, *_):
        """Shows the viewer and enters a rendering loop."""
        try:
            self._init()
            while not self.close:
                self._move_selection_into_view()
                self._render()
                self._handle_input()
        except KeyboardInterrupt:
            pass

    def select_item(self, item_id):
        """Selects the item with a specific id."""
        for item_index, item in enumerate(self.items):
            if item[0] == item_id:
                self.selected_line = item_index
                break

    def _run_subprocess(self, command):
        curses.endwin()
        subprocess.run(command)
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
        if curses.can_change_color():
            for color_index, color in enumerate(COLORS):
                curses.init_color(color_index + 1, *hex_to_rgb(color))
                curses.init_pair(color_index + 1, color_index + 1, 0)
            self.num_colors = len(COLORS)
        else:
            for color_index, color in enumerate(COLORS_FALLBACK):
                curses.init_pair(color_index + 1, color, 0)
            self.num_colors = len(COLORS_FALLBACK)

    def _read_todo_file(self):
        self.items.clear()
        with open(os.path.join(self.root, 'todo.txt'), 'r') as todofile:
            lines = todofile.readlines()
        items = [(index + 1, line) for index, line in enumerate(lines)]
        self.items = sorted(items, key=get_priority_as_number)

    def _handle_input(self):
        key = self.screen.getch()
        selected_id = self.selected_item[0]
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
        # q: quit
        elif key in (ord('q'), KEY_ESC):
            self.close = True
        # r: refresh
        elif key == ord('r'):
            self._read_todo_file()
            curses.flash()
        # d: done
        elif key == ord('d'):
            self._run_subprocess(['todo.sh', 'do', str(selected_id)])
        # n: nav
        elif key == ord('n'):
            self._run_subprocess(['todo.sh', 'nav', str(selected_id)])
        # SPACE/RETURN: Enter item dialog
        elif key in (ord(' '), ord('\n')):
            Dialog(self.selected_item).run()
        # -/=: Bump priority
        elif key in (ord('='), ord('-')):
            delta = (key == ord('=')) and 1 or -1
            new_priority = get_bumped_priority(self.selected_item, delta)
            self._run_subprocess(
                ['todo.sh', 'pri', str(selected_id), new_priority])
            self.select_item(selected_id)
        # A-Z: Set priority
        elif key >= ord('A') and key <= ord('Z'):
            self._run_subprocess(
                ['todo.sh', 'pri', str(selected_id), chr(key)])
            self.select_item(selected_id)
        # Mouse events
        # elif key == curses.KEY_MOUSE:
        #     _, _, row, _, _ = curses.getmouse()
        #     self.selected_line = row

    def _move_selection_into_view(self):
        self.selected_line = max(
            0, min(len(self.items) - 1, self.selected_line))
        if self.selected_line < self.scroll_offset:
            self.scroll_offset = self.selected_line
        elif self.selected_line > get_num_lines() + self.scroll_offset:
            self.scroll_offset = self.selected_line - get_num_lines()

    def _print(self, row, col, chunks):
        for text, attr in chunks:
            num_chars = len(text)
            if col + num_chars > get_num_columns():
                num_chars = get_num_columns() - col
            self.screen.addnstr(row, col, text, num_chars, attr)
            col += num_chars

    def _print_item(self, index, item, selected=False):
        color_index = get_priority_as_number(
            item, maximum=self.num_colors - 1) + 1
        attr = curses.color_pair(color_index) | (
            selected and curses.A_STANDOUT or 0)
        linenum, line = item
        line = re.sub(RE_PRIORITY + ' ', '', line)
        # line = re.sub(RE_CONTEXT_OR_PROJECT, r'\1', line)
        # self.screen.addnstr(
        #     index, 0, '{:02d} {:}'.format(linenum, line), get_num_columns(), attr)
        self._print(index, 0, [
            ('{:02d} '.format(linenum), attr | curses.A_DIM),
            (line, attr),
        ])

    def _render(self):
        self.screen.erase()
        top = self.scroll_offset
        bottom = self.scroll_offset + get_num_lines() + 1
        for index, item in enumerate(self.items[top:bottom]):
            self._print_item(index, item)
        self._print_item(self.selected_line - self.scroll_offset,
                         self.items[self.selected_line], True)
        self.screen.refresh()


def main():
    """Main entry point. Parses command line arguments and runs the viewer."""
    parser = argparse.ArgumentParser()
    parser.add_argument("dir")
    args = parser.parse_args()
    curses.wrapper(TodoListViewer(args.dir).run)


if __name__ == '__main__':
    main()
