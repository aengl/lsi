""" An interactive viewer for todo-txt.
"""

#!/usr/bin/env python3

import os
import re
import sys
import argparse
import curses

RE_PRIORITY = r'\(([A-Z])\)'
RE_CONTEXT_OR_PROJECT = r'([@+][^\s]+)'
COLORS = [
    '#F5D761',
    '#A4F54C',
    '#78C1F3',
    '#837CC5',
    '#CCCCCC'
]

KEY_UP = curses.KEY_UP
KEY_DOWN = curses.KEY_DOWN
KEY_ESC = 27
KEY_RETURN = 100


def get_priority(item):
    match = re.search(RE_PRIORITY, item[1])
    return match and match.group(1) or None


def get_priority_as_number(item, maximum=sys.maxsize):
    priority = get_priority(item)
    if priority == None:
        return maximum
    return min(maximum, ord(priority) - ord('A'))


def hex_to_rgb(s):
    mul = 1000 / 255
    return tuple(round(int(s.lstrip('#')[i:i + 2], 16) * mul) for i in (0, 2, 4))


class Dialog:
    """ A popup dialog that lets us interact with todo items.
    """

    def __init__(self, item):
        self.dialog = None
        self.close = False
        self.item = item
        self.actions = []

    def run(self):
        """ Shows the dialog and enters a rendering loop.
        """
        self._init()
        while not self.close:
            self._render()
            self._handle_input()

    def _init(self):
        self.dialog = curses.newwin(10, curses.COLS, 0, 0)
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
    """ A viewer that lets us browse and filter todo items.
    """

    @property
    def selected_item(self):
        return self.items[self.selected_line]

    @property
    def _num_available_lines(self):
        return curses.LINES - 2

    def __init__(self, root):
        self.root = root
        self.screen = None
        self.scroll_offset = 0
        self.selected_line = 0
        self.close = False
        self.items = []

    def run(self, *_):
        """ Shows the viewer and enters a rendering loop.
        """
        try:
            self._init()
            self._read_todo_file()
            while not self.close:
                self._render()
                self._handle_input()
        except KeyboardInterrupt:
            pass

    def _init(self):
        self.screen = curses.initscr()
        self.screen.keypad(1)
        self.screen.border(0)
        curses.noecho()
        # curses.cbreak()
        curses.curs_set(0)
        curses.start_color()
        for color_index, color in enumerate(COLORS):
            red, green, blue = hex_to_rgb(color)
            curses.init_color(color_index + 1, red, green, blue)
            curses.init_pair(color_index + 1, color_index + 1, 0)

    def _read_todo_file(self):
        self.items.clear()
        with open(os.path.join(self.root, 'todo.txt'), 'r') as todofile:
            self.items = sorted([(index + 1, line)
                                 for index, line in enumerate(todofile.readlines())], key=get_priority_as_number)

    def _handle_input(self):
        key = self.screen.getch()
        if key in (ord('k'), KEY_UP):
            self._scroll(-1)
        elif key in (ord('j'), KEY_DOWN):
            self._scroll(1)
        elif key in (ord('q'), KEY_ESC):
            self.close = True
        elif key in (ord('d'), KEY_RETURN):
            Dialog(self.selected_item).run()

    def _scroll(self, delta):
        self.selected_line = max(
            0, min(len(self.items) - 1, self.selected_line + delta))
        if self.selected_line < self.scroll_offset:
            self.scroll_offset = self.selected_line
        elif self.selected_line > self._num_available_lines + self.scroll_offset:
            self.scroll_offset = self.selected_line - self._num_available_lines

    def _print_item(self, index, item, selected=False):
        color_index = get_priority_as_number(item, maximum=len(COLORS) - 1) + 1
        attr = curses.color_pair(color_index) | (
            selected and curses.A_REVERSE or 0)
        linenum, line = item
        line = re.sub(RE_PRIORITY + ' ', '', line)
        line = re.sub(RE_CONTEXT_OR_PROJECT, r'\1', line)
        self.screen.addnstr(
            index, 0, '{:02d} {:}'.format(linenum, line), 80, attr)

    def _render(self):
        self.screen.erase()
        top = self.scroll_offset
        bottom = self.scroll_offset + self._num_available_lines + 1
        for index, item in enumerate(self.items[top:bottom]):
            self._print_item(index, item)
        self._print_item(self.selected_line - self.scroll_offset,
                         self.items[self.selected_line], True)
        self.screen.refresh()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("dir")
    parser.add_argument(
        "share", nargs="?", help="absolute or relative path to the share")
    args = parser.parse_args()
    root = args.share and os.path.abspath(
        os.path.join(args.dir, args.share)) or args.dir
    if not os.path.isdir(root):
        print("Error: %s is not a directory" % args.dir)
        sys.exit(1)
    curses.wrapper(TodoListViewer(root).run)


if __name__ == '__main__':
    main()
