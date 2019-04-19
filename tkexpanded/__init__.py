# ****** Imports ******
import tkinter.ttk as ttk
import tkinter as tk
import typing as tp
from collections import defaultdict
from configparser import ConfigParser, NoSectionError
from re import compile as regex_compile
import asyncio
import logging
import os
from sys import stderr

# ****** Import Setup ******
root_logger = logging.getLogger(__name__)
root_logger.setLevel(logging.DEBUG)

# ****** Module Variables ******
__all__ = (
    "ButtonFrame", "ApplicationBase",
    "PageBase", "PaddedNotebook", "LabelFrame",
    "IntEntry", "DoubleEntry",
)


# ****** Logging Suppression ******
_logging_enabled = False


def enable_logging(level: int = logging.DEBUG):
    from sys import stderr
    global _logging_enabled

    if not _logging_enabled:
        root_logger.setLevel(level)
        root_logger.addHandler(logging.StreamHandler(stderr))


class PaddedNotebook(ttk.Notebook):
    def __init__(self, master: tk.Misc = None, **kwargs) -> None:
        super().__init__(master, **kwargs)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.pages: tp.Dict[str, ttk.Frame] = {}

    def add_page(self, name: str) -> ttk.Frame:
        pad = ttk.Frame(self)
        pad.grid(row=0, column=0, sticky="nsew")
        pad.columnconfigure(0, weight=1)
        pad.rowconfigure(0, weight=1)
        ttk.Notebook.add(self, pad, text=name)

        tab = ttk.Frame(pad)
        tab.grid(sticky="nsew", padx=5, pady=5)

        self.pages[name] = tab
        return tab


class LabelFrame(ttk.Frame):
    def __init__(self, master: tk.Misc = None, style="TFrame", **kwargs) -> None:
        super().__init__(master, style=style, **kwargs)
        self.style = style
        self.columnconfigure(1, weight=1)
        self.num = 0

    def add_label(self, name: str) -> tp.Tuple[ttk.Label, ttk.Frame]:
        row = self.num
        self.num += 1
        label = ttk.Label(self, text=name + ":   ", anchor="e")
        label.grid(row=row, column=0, sticky="nsew")
        self.rowconfigure(row, pad=1)

        frame = ttk.Frame(self, style=self.style)
        frame.grid(row=row, column=1, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        return label, frame

    def add_separator(self, text=None) -> ttk.Frame:
        row = self.num
        self.num += 1
        if text is None:
            frame = ttk.Frame(self)
            frame.grid(row=row, column=0, sticky="nsew")
            sep = ttk.Separator(frame)
            sep.grid(row=row, column=0, sticky="nsew")
            self.rowconfigure(row, pad=5)
            return frame
        else:
            frame = ttk.Frame(self)
            frame.grid(row=row, column=0, columnspan=2, sticky="nsew")

            sep1 = ttk.Separator(frame, orient="horizontal")
            sep1.grid(row=row, column=0, sticky="ew")
            frame.columnconfigure(0, pad=20)

            label = ttk.Label(frame, text=text)
            label.grid(row=row, column=1, sticky="ew")

            sep2 = ttk.Separator(frame, orient="horizontal")
            sep2.grid(row=row, column=2, sticky="ew")
            frame.columnconfigure(2, weight=1)
            self.rowconfigure(row, pad=5)
            return frame


class DoubleEntry(ttk.Entry):
    def __init__(self, master: tk.Misc = None, widget=None, **kwargs):
        # vcmd = (master.register(self.validate_is_number), "%d", "%i", "P", "%s", "%S", "%v", "%V", "%W")
        vcmd = (master.register(self.validate_is_number))

        super().__init__(master, widget, validate="all", validatecommand=(vcmd, "%P"), **kwargs)
        # super().__init__(master, widget, **kwargs)

        # ****** Bindings ******
        # self.bind("<Key>", self.check_entry)
        # self.bind("<Return>", lambda e=None: print(self.current_index))

    def validate_is_number(self, text):
        try:
            float(text)
            return True
        except ValueError:
            return False

    def check_entry(self, event):
        from re import match
        """This is a partial solution to the problem.
        Currently does not work."""
        widget: ttk.Entry = self
        text: str = widget.get()
        current_index: int = widget.index("insert")
        skip_check = False
        require_reword = True
        key = event.keysym

        if key not in ("BackSpace", "Delete", "period") and len(key) > 1:
            if key == "End":
                require_reword = False
                skip_check = True
                current_index = len(text)

            elif key == "Home":
                require_reword = False
                skip_check = True
                current_index = 0

            elif key in ("Left", "Right"):
                if key == "Left":
                    if current_index == 0:
                        pass
                    else:
                        current_index -= 1
                else:
                    if current_index > len(text) - 1:
                        pass
                    else:
                        current_index += 1
                # this much just to get the index right?
                require_reword = False
                skip_check = True
            else:
                # we can't possibly make a list of all non-integer characters.
                skip_check = True

        if not skip_check:
            if key.isdecimal():
                insert_char = key
            elif key == "period" and "." not in text:
                insert_char = "."
            else:
                insert_char = ""

            if bool(insert_char):
                current_index += 1

            if current_index < len(text) + 1:
                check = text[0:current_index - 1] + insert_char + text[current_index - 1:]
            else:
                check = text + insert_char

            if key == "BackSpace":
                if current_index == 0:
                    pass
                else:
                    check = check[:-1]
                    current_index -= 1
            elif key == "Delete":
                check = check[:current_index] + text[current_index+1:]

            smatch = match("(0+[1-9][0-9]*).?([0-9]*)", check)

            if check == "":
                check = "0"
            elif smatch:
                check = check.lstrip("0")
                current_index -= 1
            text = check

        def reword():
            widget.delete("0", "end")
            widget.insert("insert", text)

        if require_reword:
            self.after_idle(reword)

        self.after_idle(lambda: widget.icursor(current_index))


class IntEntry(DoubleEntry):
    def validate_is_number(self, text):
        try:
            int(text)
            return True
        except ValueError:
            return False


# ****** ButtonFrame Widget ******
class ButtonFrame(ttk.Frame):
    """Ttk Frame widget containing left and right buttons,
    names and commands supplied as dicts of keys and values
    respectively."""
    def __init__(self, master: tk.Misc, **kwargs) -> None:
        super().__init__(master, **kwargs)

        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)

        self.left: tp.Dict[str, ttk.Button] = {}
        self.right: tp.Dict[str, ttk.Button] = {}

    def make_buttons(
            self, left: tp.Dict[str, tp.Callable[[tk.Event], None]],
            right: tp.Dict[str, tp.Callable[[tk.Event], None]]
    ) -> None:
        left_buttons = ttk.Frame(self)
        left_buttons.grid(row=0, column=0, sticky="nsw")

        right_buttons = ttk.Frame(self)
        right_buttons.grid(row=0, column=1, sticky="nse")

        # ****** Left Button Widgets ******
        for i, key in enumerate(left):
            left_buttons.columnconfigure(i, pad=9)
            lb = ttk.Button(
                left_buttons,
                text=key,
                width=11,
                command=left[key])
            lb.grid(row=0, column=i)
            lb.bind("<Return>", lb["command"])
            self.left[key] = lb

        # ****** Right Button Widgets ******
        for i, key in enumerate(right):
            right_buttons.columnconfigure(i, pad=9)
            rb = ttk.Button(
                right_buttons,
                text=key,
                width=11,
                command=right[key])
            rb.grid(row=0, column=i)
            rb.bind("<Return>", rb["command"])
            self.right[key] = rb


class PageMaster(ttk.Frame):
    def __init__(self, master: "ApplicationBase", **kwargs):
        super(PageMaster, self).__init__(master, **kwargs)

        self.pages: tp.Dict[tp.Hashable, "PageBase"] = {}
        self.indices: tp.Dict[tp.Hashable, tp.Tuple[int, int]] = {}
        self.matrix: tp.Dict[int, tp.Dict[int, tp.Hashable]] = defaultdict(dict)

    # ****** Setup PageMaster as Dict ******
    def __getitem__(self, name: tp.Hashable) -> "PageBase":
        if name not in self.names():
            raise KeyError("Page " + str(name) + " has not been registered.")
        return self.pages[name]

    # ****** Page System ******
    def register(
            self, cont: tp.Type["PageBase"], name: tp.Hashable, row: int,
            column: int, *args, **kwargs
    ) -> None:
        """Register a page with the PageMaster."""
        if type(cont) is type:
            page = cont(self, *args, **kwargs)
        else:
            page = cont
        self.pages[name] = page
        self.indices[name] = (row, column)
        # page.grid(row=row, column=col, sticky="nsew")
        self.rowconfigure(row, weight=1)
        self.columnconfigure(column, weight=1)

    def names(self) -> tp.Tuple[tp.Hashable, ...]:
        """Return a tuple of the names of all registered pages."""
        return tuple(self.pages.keys())

    def forget(self, *names: str) -> None:
        """Forget all pages in :param names:"""
        for key in names:
            page = self[key]
            if page.active:
                page.exit()
                page.active = False
            page.grid_forget()

    def show(self, name: tp.Hashable, row=None, col=None, **kwargs) -> None:
        """Display the given page"""
        try:
            page = self[name]
            if row is None and col is None:
                row, col = self.indices[name]
            elif row is None:
                col = self.indices[name][1]
            elif col is None:
                row = self.indices[name][0]

            # check to see if the page covers another
            try:
                cur_page_name: str = self.matrix[row][col]
                cur_page: PageBase = self[cur_page_name][0]
                if hasattr(page, "exit"):
                    if cur_page.active:
                        cur_page.exit()
                        cur_page.active = False
                cur_page.grid_forget()
            except KeyError:
                # no previous page
                pass

            self.matrix[row][col] = name
            if hasattr(page, "enter"):
                page.enter()
            page.grid(row=row, column=col, sticky="nsew", **kwargs)
            page.tkraise()
            page.active = True
        except KeyError:
            raise KeyError("Page " + str(name) + " has not been registered.")

    def get(self, name: tp.Hashable, default=None):
        try:
            return self[name]
        except KeyError:
            return default

    # ****** Overwritten Methods ******
    def destroy(self):
        root_logger.debug("Destroying Page Master")
        try:
            for page in self.pages.values():
                if hasattr(page, "exit"):
                    if page.active:
                        page.exit()
                page.grid_forget()
                page.destroy()
        except tk.TclError:
            raise tk.TclError("A widget was destroyed, then it was referenced in a function call.")

    # ****** Command System ******
    def message(self, name: tp.Hashable, command: tp.Hashable, *args, **kwargs):
        """Every instance of PageBase has a reference to its master,
        so we can possibly use this fact to send messages to pages
        instead of being sneaky with the Variable traces."""
        self[name].dispatch(command, *args, **kwargs)


class PageBase(ttk.Frame):
    __slots__ = ("active", "master")
    """Abstract Base Class for Page types"""
    def __init__(self, master: PageMaster, *args, **kwargs) -> None:
        super(PageBase, self).__init__(master, **kwargs)

        # ****** Attribute Definition ******
        self.master = master
        self.active = False

        # ****** Command System ******
        self._commands: tp.Dict[tp.Hashable, tp.Callable[[], None]] = {}

        # ****** Page Initialization ******
        self.create()

    # ****** Command System ******
    def dispatch(self, command: tp.Hashable, *args, **kwargs):
        self._commands[command](*args, **kwargs)

    def command_add(self, name: tp.Hashable, func: tp.Callable[[], None]):
        self._commands[name] = func

    def command_remove(self, name: tp.Hashable):
        del self._commands[name]

    def command_names(self):
        return self._commands.keys()

    # ****** Page System ******
    def create(self):
        """Creates the pages's widgets."""
        pass

    def enter(self) -> None:
        """Will be called every time this page is shown."""
        pass

    def exit(self) -> None:
        """Will be called every time this page is hidden."""
        pass

    # ****** Overwritten Methods ******
    def destroy(self) -> None:
        super().destroy()


class ApplicationBase(tk.Tk):
    def __init__(
            self, loop: asyncio.AbstractEventLoop,
            icon: str = None, title: str = None, *args,
            **kwargs
    ) -> None:
        super().__init__(*args, **kwargs)

        # ****** Attributes ******
        self.loop = loop

        # ****** Setup ******
        self.protocol("WM_DELETE_WINDOW", self.__destroy)
        self.toggle()
        self.title(title)

        try:
            self.iconbitmap(icon)
        except tk.TclError:
            root_logger.warning("Icon file not found. Using default tkinter icon.")
            pass

    def destroy(self):
        self.toggle()

        if hasattr(self, "exit"):
            self.exit()

        async def stop_mainloop():
            nonlocal self
            self.loop.stop()
            super(ApplicationBase, self).destroy()

        for task in asyncio.Task.all_tasks():
            root_logger.debug("Stopping " + str(task))
            task.cancel()
        asyncio.ensure_future(stop_mainloop(), loop=self.loop)

    __destroy = destroy

    async def _update_window(self, interval):
        while True:
            try:
                self.update()
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                root_logger.info("Stopping mainloop.")
                raise

    def mainloop(self, n=1/20):
        try:
            self.loop.create_task(self._update_window(n))
            self.loop.run_forever()
        except SystemExit:
            self.__destroy()
            raise
        finally:
            self.loop.close()

    __mainloop = mainloop

    @staticmethod
    def ms_loop(master: tk.Tk, ms: int):
        def decorator(func):
            def wrapper(*args):
                keep_alive = func()
                if keep_alive:
                    master.after(ms, wrapper, *args)
            return wrapper
        return decorator

    @staticmethod
    def idle_loop(master: tk.Tk):
        def decorator(func):
            def wrapper(*args):
                keep_alive = func(*args)
                if keep_alive:
                    master.after_idle(wrapper, *args)
            return wrapper
        return decorator

    def center(self) -> None:
        self.update_idletasks()
        width: int = self.winfo_width()
        frm_width: int = self.winfo_rootx() - self.winfo_x()
        win_width = width + 2 * frm_width
        height: int = self.winfo_height()
        titlebar_height: int = self.winfo_rooty() - self.winfo_y()
        win_height = height + titlebar_height + frm_width
        x: int = self.winfo_screenwidth() // 2 - win_width // 2
        y: int = self.winfo_screenheight() // 2 - win_height // 2
        self.geometry('{}x{}+{}+{}'.format(width, height, x, y))
        self.deiconify()

    def toggle(self) -> None:
        self.attributes("-alpha", float(not self.attributes("-alpha")))

    def run(self):
        self.center()
        self.toggle()
        self.__mainloop()
