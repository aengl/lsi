# lsi
An interactive viewer for [todo.txt](https://github.com/ginatrapani/todo.txt-cli).

## Setup on macOS

Install `todo-txt`:

    brew install todo-txt

Then, configure your TODO_DIR by editing the config file in `~/.todo/config`.

To install this extension:

    cd ~/.todo.actions.d
    git clone https://github.com/aengl/lsi.git

If the directory doesn't exist, create it manually first.

## Usage

Run the interactive viewer with:

    todo.sh lsi

## Keyboard shortcuts

- `j/k/up/down`: navigate items
- `home/end`: scroll to top/bottom
- `q/esc`: cancel filter or quit
- `r`: refresh
- `e`: edit todo.txt file (requires [edit add-on](https://github.com/ginatrapani/todo.txt-cli/wiki/Todo.sh-Add-on-Directory#edit-open-in-text-editor))
- `/`: start filtering
- `d`: mark item as done
- `n`: navigate to the URL in an item (requires [nav add-on](https://github.com/ginatrapani/todo.txt-cli/wiki/Todo.sh-Add-on-Directory#nav-open-items-url-in-browser))
- `space/return`: enter dialog (doesn't have much of a point right now and might get removed soon)
- `-/=`: increase/decrease item priority
- `A-Z`: set item priority
- `0`: unset item priority

## Command line arguments

- You can pass an optional positional argument that will apply an initial filter.
- `--simple`: Enters simple mode for terminals that don't support defining custom colors. `Terminal` on macOS will need this, but `iTerm` will work fine without it.
