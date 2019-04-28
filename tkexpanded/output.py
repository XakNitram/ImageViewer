from typing import (
    Dict, Tuple, NewType, Any,
    Callable, Optional, Hashable
)
from tkinter import Misc, EventType, TclError
from tkinter.scrolledtext import ScrolledText
from functools import singledispatch
from re import sub, escape


# ****** Messageboard ******


# ****** Type Aliases ******
Index = NewType("Index", str)


# ****** Module Globals ******
Streams: Dict[Hashable, "Output"] = {}


class ViolatedLock(Exception):
    pass


class Block:
    """A block of text contained within a tkinter.Text object"""

    def __init__(self, window: "Output", name: str, start: Index, text: str):
        # ****** Attributes ******
        self.window = window  # text window associated with text block
        self.window.mark_set(name, start)
        self.window.mark_gravity(name, "left")

        self.text = text
        self.name = name

        self.start = start
        self.end = self._calculate_end()
        self.indices: Tuple[Index, Index] = (start, self.end)

        self.locked = False
        self.hidden = True
        self._hidden_inplace = False

    def update(self, *text: str, sep=" ", end="\n"):
        if self.locked:
            raise ViolatedLock(
                "A block of text should not be edited while it has not been displayed."
            )

        # allow editing of the text on the window
        self.window.configure(state="normal")

        # construct the text
        t: str = sep.join(map(str, text)) + str(end)

        # remove the previous text
        self.window.delete(self.name, self.end)

        # split the index
        index: Index = self.window.index(self.name)

        # insert the new text
        self.window.insert(index, t)
        self.text = t
        self.end = self._calculate_end()

        # return the text window to a read-only state
        self.window.configure(state="disabled")

        if self.hidden:
            self.hide(self._hidden_inplace)

    def update_tags(self):
        self.window.tag_remove(self.name, self.start, self.name + ".last")
        self.window.tag_add(self.name, self.start, self.end)

    def show(self):
        if not self.hidden:
            return

        if self.locked:
            raise ViolatedLock(
                "A block of text should not be edited while it has not been displayed."
            )

        self.window.configure(state="normal")

        if self._hidden_inplace:
            self.window.delete(self.start, self.end)
            self._hidden_inplace = False

        self.window.insert(self.start, self.text)
        self.window.configure(state="disabled")

        self.hidden = False

    def hide(self, inplace=False):
        if self.hidden:
            return

        self.window.configure(state="normal")
        self.window.delete(self.name, self.end)
        if inplace:
            text = sub(r".", " ", self.text)
            self.window.insert(self.start, text)

            self._hidden_inplace = True

        self._calculate_end()
        self.window.configure(state="disabled")

        self.hidden = True

    def goto(self):
        self.window.yview(self.name)

    def add_link(self, func: Callable[[], None]):
        def link(name):
            self.window.config(cursor="hand2")
            self.window.tag_config(name, foreground="#428BF0", underline=1)

        def unlink(name):
            self.window.config(cursor="arrow")
            self.window.tag_config(name, foreground=self.window["foreground"], underline=0)

        def tag_keys(name):
            def _tag(event):
                et = event.type
                if et == EventType.KeyPress and event.keysym == "Control_L":
                    link(name)
                else:
                    unlink(name)
            return _tag

        def tag_do():
            func()

        self.window.tag_add(self.name, self.start, self.end)
        self.window.tag_bind(self.name, "<Control-Enter>", lambda event: link(self.name))
        self.window.tag_bind(self.name, "<Leave>", lambda event: unlink(self.name))
        self.window.tag_bind(self.name, "<KeyRelease>", tag_keys(self.name))
        self.window.tag_bind(self.name, "<KeyPress>", tag_keys(self.name))
        self.window.tag_bind(self.name, "<Control-Button-1>", tag_do())

    # ****** Helpers ******
    def _calculate_end(self) -> Index:
        # indices in tkinter are stored as a string
        #   of the format 'row.column'
        row, col = tuple(map(int, self.start.split(".")))

        ns = self.text.count("\n")

        if ns >= 1:
            rows = str(row + ns)
            len_text = len(self.text.split("\n")[-1])
        else:
            rows = str(row)
            len_text = len(self.text)

        # update the end index.
        end = Index(rows + "." + str(len_text))
        return end

    def __del__(self):
        # cleanup
        try:
            self.window.mark_unset(self.name)
        except TclError:
            # output has been destroyed, so
            # no need to unset the mark.
            pass

    def __repr__(self):
        window = self.window
        return "{}: {} to {} '{}'".format(
            self.__class__.__name__,
            window.index(self.start),
            window.index(self.end),
            self.text.strip("\n\t\r")
        )


class Output(ScrolledText):
    def __init__(self, master: Misc = None, **kwargs) -> None:
        super().__init__(master, **kwargs)
        # make the widget read-only, as consistent with the idea of an output
        self.configure(state="disabled")

        # setup style defaults
        self.configure(
            bg=kwargs.get("bg") or kwargs.get("background") or "#293134",
            fg=kwargs.get("fg") or kwargs.get("foreground") or "#E0E2E4",
            selectbackground=kwargs.get("selectbackground", "#2F393C"),
            selectforeground=kwargs.get("selectforeground", "#557dac"),
            font=kwargs.get("font", ("Verdana", "10")),
        )

        # ****** Attribute Definitions ******
        self.block_count: int = 0

    def scroll_to_top(self) -> None:
        self.yview("1.0")

    def scroll_to_bottom(self) -> None:
        self.yview("end")

    def create_block(
            self, *text: Any, sep: str = " ",
            end: str = "\n"
    ) -> Block:
        # join text
        con_text = str(sep).join(map(str, text)) + str(end)

        # create block
        index = Index(self.index("insert"))
        block = Block(self, f"block{self.block_count}", index, con_text)

        # increment block count
        self.block_count += 1

        return block

    def display(
            self, *text: Any, end: str = '\n',
            sep: str = ' ', scroll: bool = True
    ) -> Block:
        """
        Functions similar to python's built-in print()
        """
        block = self.create_block(*text, sep=sep, end=end)
        block.show()

        # ****** Scroll ******
        self.update_idletasks()
        if scroll:
            self.yview("end")

        return block

    def display_after(
            self, ms: int, *text, sep: str = " ",
            end: str = "\n", scroll=True
    ) -> Block:
        block = self.create_block(*text, sep=sep, end=end)

        def unlock(event=None):
            nonlocal block
            block.locked = False
            block.show()

            if scroll:
                block.goto()

        self.after(ms, unlock, *text)
        return block

    def clear(self) -> None:
        """Removes all text from the output window"""
        self['state'] = 'normal'
        self.delete('1.0', 'end')
        self['state'] = 'disabled'

    def write(self, text):
        self.display(text, sep="", end="")


@singledispatch
def display(
        stream, *text: Any, end: str = '\n',
        sep: str = ' '
) -> Optional[Block]:
    display_stream = Streams.get(stream)
    if display_stream is None:
        return None

    block = display_stream.display(
        *text, end=end, sep=sep
    )
    return block


# handle multiple streams
@display.register(list)
@display.register(tuple)
def _(streams, *text: Any, end: str = "\n", sep: str = " ") -> Tuple[Optional[Block]]:
    blocks = []
    for stream in streams:
        output = Streams.get(stream)
        if output is None:
            blocks.append(None)
            continue

        block = output.display(
            *text, end=end, sep=sep
        )
        blocks.append(block)
    return tuple(blocks)


if __name__ == '__main__':
    import tkinter as tk
    from itertools import compress

    _root = tk.Tk()

    _kwargs = dict()
    _kwargs.update(width=20, height=5)

    _out1 = Output(_root, **_kwargs)
    _out1.pack()

    _out2 = Output(_root, **_kwargs)
    _out2.pack()

    Streams["out1"] = _out1
    Streams["out2"] = _out2

    _blocks: Tuple[Optional[Block]] = display(["out1", "out2", "out3"], "this")
    for _block in compress(_blocks, [blk is not None for blk in _blocks]):
        _block.update("this2\nthis")
        print(_block)
    display("out1", "this")
    _root.mainloop()
