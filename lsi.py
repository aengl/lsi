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


class TodoListViewer:
    @property
    def num_available_lines(self):
        return curses.LINES - 2

    def __init__(self, root):
        self.root = root
        self.screen = None
        self.scroll_offset = 0
        self.selected_line = 0
        self.quit = False
        self.items = []

    def init_screen(self):
        self.screen = curses.initscr()
        self.screen.keypad(1)
        self.screen.border(0)
        curses.noecho()
        curses.cbreak()
        curses.curs_set(0)
        self.init_colors()

    def init_colors(self):
        curses.start_color()
        for color_index, color in enumerate(COLORS):
            red, green, blue = hex_to_rgb(color)
            curses.init_color(color_index + 1, red, green, blue)
            curses.init_pair(color_index + 1, color_index + 1, 0)

    def read_todo_file(self):
        self.items.clear()
        with open(os.path.join(self.root, 'todo.txt'), 'r') as todofile:
            self.items = sorted([(index + 1, line)
                                 for index, line in enumerate(todofile.readlines())], key=lambda x: get_priority_as_number(x))

    def run(self, *args, **kwargs):
        try:
            self.init_screen()
            self.read_todo_file()
            while not self.quit:
                self.display_screen()
                self.handle_input()
        except KeyboardInterrupt:
            pass

    def handle_input(self):
        c = self.screen.getch()
        if c == curses.KEY_UP:
            self.scroll(-1)
        elif c == curses.KEY_DOWN:
            self.scroll(1)
        elif c == 27:  # ESC_KEY
            self.quit = True

    def print_item(self, index, item, selected=False):
        color_index = get_priority_as_number(item, maximum=len(COLORS) - 1) + 1
        attr = curses.color_pair(color_index) | (
            selected and curses.A_BOLD or 0)
        linenum, line = item
        line = re.sub(RE_PRIORITY + ' ', '', line)
        line = re.sub(RE_CONTEXT_OR_PROJECT, r'\1', line)
        self.screen.addnstr(
            index, 0, '{:02d} {:}'.format(linenum, line), 80, attr)

    def display_screen(self):
        self.screen.erase()
        top = self.scroll_offset
        bottom = self.scroll_offset + self.num_available_lines + 1
        for index, item in enumerate(self.items[top:bottom]):
            self.print_item(index, item)
        self.print_item(self.selected_line - self.scroll_offset,
                        self.items[self.selected_line], True)
        self.screen.refresh()

    def scroll(self, delta):
        self.selected_line = max(
            0, min(len(self.items) - 1, self.selected_line + delta))
        if self.selected_line < self.scroll_offset:
            self.scroll_offset = self.selected_line
        elif self.selected_line > self.num_available_lines + self.scroll_offset:
            self.scroll_offset = self.selected_line - self.num_available_lines


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
