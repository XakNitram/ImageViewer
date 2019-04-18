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
    "Output", "ButtonFrame", "ApplicationBase",
    "PageBase", "PaddedNotebook", "LabelFrame",
    "IntEntry", "DoubleEntry", "VariableDict",
    "Streams", "display"
)

# ****** Type Aliases ******
SupportedTypes = tp.Union[str, int, float, bool]
VariableT = tp.Union[tk.Variable, tk.StringVar, tk.IntVar, tk.DoubleVar, tk.BooleanVar]
TkContainer = tp.Union[tk.Tk, tk.Toplevel, tk.Frame, tk.Canvas, ttk.Frame, ttk.Panedwindow]
SettingsDict = tp.Dict[tp.AnyStr, VariableT]
Index = tp.NewType("Index", str)

# ****** Globals ******
TYPE_MAPPING = {str: tk.StringVar, int: tk.IntVar, float: tk.DoubleVar, bool: tk.BooleanVar}
Streams: tp.Dict[str, "Output"] = {}


# ****** Logging Suppression ******
_logging_enabled = False


def enable_logging(level: int = logging.DEBUG):
    from sys import stderr
    global _logging_enabled

    if not _logging_enabled:
        root_logger.setLevel(level)
        root_logger.addHandler(logging.StreamHandler(stderr))


class Output(tk.Text):
    # TODO: Make the 'display' method return the name of a mark that
    #   the user can use to refer back to the text they inserted.

    def __init__(self, master: TkContainer=None, **kwargs) -> None:
        # ****** Main Container Definition******
        self.frame = ttk.Frame(master)
        # this frame is required because the scrollbar
        # cannot be placed within a text frame.
        # ****** Scrollbar Definition ******
        self.vbar = ttk.Scrollbar(self.frame)
        self.vbar.pack(side="right", fill="y")

        # ****** Text Widget Definition ******
        kwargs.update({"yscrollcommand": self.vbar.set})
        tk.Text.__init__(self, self.frame, **kwargs)
        self.pack(side="left", fill="both", expand=True)
        self.vbar["command"] = self.yview
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

        # ****** Method Reassignment ******
        # since the text widget is not the only widget being
        # placed, the placing methods have to be reassigned
        # to the frame that contains the text widget.
        text_meths = vars(tk.Text).keys()
        methods = set(vars(tk.Pack).keys() | vars(tk.Grid).keys() | vars(tk.Place).keys())
        methods = methods.difference(text_meths)

        for m in methods:
            if m[0] != "_" and m not in ("config", "configure"):
                setattr(self, m, getattr(self.frame, m))

        # ****** Variable Definitions ******
        self.dynamic_marks: tp.Dict[str, tp.Tuple[Index, Index]] = {}

    def scroll_to_top(self) -> None:
        self.yview("1.0")

    def scroll_to_bottom(self) -> None:
        self.yview("end")

    def remove_mark(self, mark: str) -> None:
        try:
            self.mark_unset(mark)
            del self.dynamic_marks[mark]
        except KeyError:
            pass

    def display(
            self, *text: tp.Any, end: str= '\n',
            sep: str=' ', dynamic: bool=False,
            mark: str=None, autoscroll: bool=True
    ) -> None:
        """
        Functions similar to python's built-in print()

        If dynamic is true, a mark_name must be supplied
        and text.mark_unset(mark_name) must be used to
        clear the mark for further use.
        """
        self['state'] = 'normal'
        t: str = sep.join(map(str, text)) + str(end)
        index: Index = self.index("end")
        if dynamic:
            # ****** Required Assertions ******
            assert (mark is not None and isinstance(mark, str)), "if dynamic flag is used, mark must be of type str"
            assert mark not in ("insert", "current", "end"), "mark name cannot be a built-in"

            # ****** Mark Creation or Retrieval ******
            if mark not in self.mark_names():
                # assume this is the first call to this mark
                self.mark_set(mark, "insert")
                self.mark_gravity(mark, "left")
            else:
                # assume the mark has already been set
                mark_end: Index = Index(self.dynamic_marks[mark][1] + ("+1c" if end == "\n" else ""))
                self.delete(mark, mark_end)

            # ****** Split the Index ******
            mi: Index = self.index(mark)
            mark_comps = tuple(map(int, mi.split(".")))

            # count the number of "\n"'s
            ns = t.count("\n")
            # ****** Multi-line Case Handling ******
            if ns >= 1 and end != "\n":
                rows = str(mark_comps[0] + ns)
                l_text = len(t.split("\n")[-1])
            elif ns >= 1 and end == "\n":
                rows = str(mark_comps[0] + (ns - 1))
                l_text = len(t.split("\n")[-2]) + 1
            else:
                rows = str(mark_comps[0])
                l_text = len(t)

            # ****** Dictionary Update ******
            self.dynamic_marks[mark] = (Index(mi), Index(rows + "." + str(l_text)))
            # Where to inser the text
            index = mi

        # ****** Insert Text ******
        self.insert(index, t)
        self['state'] = 'disabled'

        # ****** Scroll ******
        self.update_idletasks()
        if autoscroll:
            self.yview("end")

    def display_with_link(self, path, end="\n"):
        from os import startfile
        from os.path import split

        def link(name):
            self.config(cursor="hand2")
            self.tag_config(name, foreground="#428BF0", underline=1)

        def unlink(name):
            self.config(cursor="arrow")
            self.tag_config(name, foreground=self["foreground"], underline=0)

        def tag_keys(name):
            def _tag(event):
                et = event.type
                if et == tk.EventType.KeyPress and event.keysym == "Control_L":
                    link(name)
                else:
                    unlink(name)
            return

        def tag_do(name):
            def _tag(event):
                try:
                    startfile(path)
                except FileNotFoundError:
                    pass

        t = str(path) + str(end)
        snl = len(str(path))
        index1 = self.index("insert")
        index2 = index1.split(".")[0] + "." + str(snl + 3)
        self.configure(state="normal")
        self.insert(index1, t)
        self.configure(state="disabled")

        # tag work
        tn = "Line" + str(int(index1.split(".")[0]) + 1) + "C"
        self.tag_add(tn, index1, index2)
        self.tag_bind(tn, "<Control-Enter>", lambda event: link(tn))
        self.tag_bind(tn, "<Leave>", lambda event: unlink(tn))
        self.tag_bind(tn, "<KeyRelease>", tag_keys(tn))
        self.tag_bind(tn, "<KeyPress>", tag_keys(tn))
        folder_path = split(path)[0]
        self.tag_bind(tn, "<Control-Button-1>", tag_do(tn))

    __display = display

    def display_after(self, ms: int, *text: str) -> None:
        self.after(ms, self.__display, *text)

    def clear(self) -> None:
        """Removes all text from the output window"""
        self['state'] = 'normal'
        self.delete('1.0', 'end')
        self['state'] = 'disabled'


def display(
        stream: str, *text: tp.Any, end: str= '\n',
        sep: str=' ', dynamic: bool=False, mark: str=None
) -> None:
    display_stream = Streams.get(stream)
    if display_stream is not None:
        display_stream.display(
            *text, end=end, sep=sep, dynamic=dynamic, mark=mark
        )


class PaddedNotebook(ttk.Notebook):
    def __init__(self, master: TkContainer=None, **kwargs) -> None:
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
    def __init__(self, master: TkContainer=None, style="TFrame", **kwargs) -> None:
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
    def __init__(self, master: TkContainer=None, widget=None, **kwargs):
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
    def __init__(self, master: TkContainer, **kwargs) -> None:
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


class VariableDict(dict, tp.Dict[str, VariableT]):
    ALLOW_OVERWRITE = False
    IGNORE_TYPE_INCOMPATIBILITIES = IGNORE_TYPE_INCOMPATS = False
    ALLOW_IMPLICIT_CREATION = False  # if a key does not exist, create it?
    ALLOW_IMPLICIT_ASSIGNMENT = True  # if a value is a builtin,

    def __init__(self, name: str, master: TkContainer=None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.master = master
        self.name = name

    def __setitem__(self, key: str, value: tp.Union[VariableT, SupportedTypes]) -> None:
        existing: VariableT = self.get(key)
        if not isinstance(value, tk.Variable):
            if existing is None:
                if self.ALLOW_IMPLICIT_CREATION:
                    meta = TYPE_MAPPING.get(type(value))
                    if meta is None:
                        if not self.IGNORE_TYPE_INCOMPATIBILITIES:
                            raise TypeError(
                                f"Type: {type(value)} is not supported."
                            )
                        else:
                            meta = tk.Variable
                    super().__setitem__(
                        key, meta(
                            master=self.master,
                            name=f"{key}_{self.name}",
                            value=value,
                        )
                    )
                    return None
                else:
                    raise KeyError(key)
            else:
                if self.ALLOW_IMPLICIT_ASSIGNMENT:
                    # allow tcl to typecheck the value and raise any errors.
                    existing.set(value)
                    return None
                else:
                    raise TypeError(
                        "Value is not an instance of tkinter.Variable "
                        "and implicit assignment is disallowed."
                    )

        elif existing is not None and existing._name == value._name:
            error_message = (
                    "Overwriting an instance of Variable with another instance with the same "
                    "name attribute is a bad idea.\ntkinter will delete both instances and "
                    "your data will be lost.\nAssert the ALLOW_OVERWRITE attribute "
                    "to supress this error."
                )
            if not self.ALLOW_OVERWRITE:
                raise ValueError(error_message)
            else:
                root_logger.error(error_message)
        super().__setitem__(key, value)

    @classmethod
    def from_mapping(cls, mapping: tp.Dict[str, tp.Any], name: str, master: TkContainer) -> "VariableDict":
        rdict = cls(name, master)
        for key, value in mapping.items():
            meta: tp.Type[VariableT] = TYPE_MAPPING.get(type(value), tk.Variable)
            if meta is None:
                if not cls.IGNORE_TYPE_INCOMPATIBILITIES:
                    raise ValueError(
                        f"Type: {type(value)} is not supported."
                    )
                else:
                    meta = tk.Variable
            rdict[key] = meta(master=master, name=f"{key}_{name}", value=value)

        return rdict

    @classmethod
    def from_existing(cls, other: "VariableDict", name: str, master: TkContainer=None) -> "VariableDict":
        rdict = cls(name, master)
        for key, value in other.items():
            meta: tp.Type[VariableT] = type(value)
            rdict[key] = meta(master=master, name=f"{key}_{name}", value=value.get())

        return rdict

    def update(self, __m: "VariableDict" = None, file: str = None, **kwargs) -> None:
        """D.update([E, ]**F) -> None. Update D from dict/iterable E and F"""
        if __m is None:
            __m = {}

        keys = set(kwargs.keys() | __m.keys())
        for key in keys:
            if key not in self:
                continue

            """
            Prefer kwargs because if the user is explicitly 
            passing a keyword argument, they probably want it
            to take precedence over a passed dictionary.
            """
            value = kwargs.get(key) or __m.get(key)
            if value is None:
                continue

            if isinstance(value, tk.Variable):
                try:
                    self[key].set(value.get())
                except KeyError:
                    meta: tp.Type[VariableT] = type(value)
                    self[key] = meta(
                        master=self.master,
                        name=f"{key}_{self.name}",
                        value=value.get()
                    )
            else:
                if self.ALLOW_IMPLICIT_ASSIGNMENT:
                    self[key].set(value)
                else:
                    raise TypeError(
                        "Value is not an instance of tkinter.Variable "
                        "and implicit assignment is disallowed."
                    )

    def import_from_file(
            self, file: str, section: str = None, pattern: str = None,
            ignore: tp.Tuple[str, ...] = None, **kwargs
    ) -> None:
        """
        Update keys in VariableDict from options in given file

        :param file: name of file to open
        :param section: name of section in file to import from
        :param pattern: names = re.findall(<pattern>, self.keys())
        :param ignore: tuple of keys to ignore on import
        """
        if not os.path.exists(file):
            raise FileNotFoundError(f"No file: '{file}'")

        if section is None:
            section = "Settings"

        settings = ConfigParser(**kwargs)
        settings.read(file)
        if not settings.has_section(section):
            raise NoSectionError(f"No section: '{section}'")

        if pattern is None:
            pattern = r"([a-zA-Z0-9]+)"
        option_regex = regex_compile(pattern)

        for key, value in self.items():
            if key in ignore:
                continue

            key_reg: tp.Tuple[str, ...] = option_regex.findall(key)
            lkey = "".join(key_reg)
            fallback = value.get()

            try:
                if isinstance(value, tk.BooleanVar):
                    x = settings.getboolean(
                        section, lkey,
                        fallback=fallback
                    )
                elif isinstance(value, tk.IntVar):
                    x = settings.getint(
                        section, lkey,
                        fallback=fallback
                    )
                elif isinstance(value, tk.DoubleVar):
                    x = settings.getfloat(
                        section, lkey,
                        fallback=fallback
                    )
                else:
                    x = settings.get(
                        section, lkey,
                        fallback=fallback
                    )
            except ValueError:
                root_logger.debug(f"Value Error on Import. Key: {key}, Type: {type(value)}")
                x = fallback
            value.set(x)

    def export_to_file(
            self, file: str, section: str = None, pattern: str = None,
            ignore: tp.Tuple[str, ...] = None, **kwargs
    ):
        """
        Export keys in VariableDict but not in ignore to given file
        file.write(set(self.keys() | set(ignore)))

        :param file: name of file to open
        :param section: name of section in file to export to
        :param pattern: names = re.findall(<pattern>, self.keys)
        :param ignore: tuple of keys to ignore on export
        """
        if section is None:
            section = "Settings"

        config = ConfigParser(**kwargs)
        config.read(file)

        if not config.has_section(section):
            config.add_section(section)

        if pattern is None:
            pattern = r"([a-zA-Z0-9]+)"
        option_regex = regex_compile(pattern)

        for key, value in self.items():
            if key in ignore or not isinstance(value, tk.Variable):
                continue

            key_reg: tp.Tuple[str, ...] = option_regex.findall(key)
            lkey = "".join(key_reg)

            config.set(section, lkey, str(value.get()))

        with open(file, "w") as config_file:
            config.write(config_file)

    def get_true(self, key) -> tp.Union[str, float, int, bool]:
        return self[key].get()


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
