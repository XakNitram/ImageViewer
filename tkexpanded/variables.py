from typing import Generic, TypeVar, Dict, Union, Any, Tuple, Type
from tkinter import Variable, StringVar, IntVar, DoubleVar, BooleanVar
from tkinter import Misc
import os
from configparser import ConfigParser, NoSectionError
from re import compile as regex_compile
import logging


__all__ = ("ObjectVar", "VariableDict")

# ****** Import Setup ******
root_logger = logging.getLogger(__name__)
root_logger.setLevel(logging.DEBUG)


# ****** Types ******
T = TypeVar("T")


# ****** Module Globals ******
TYPE_MAPPING = {str: StringVar, int: IntVar, float: DoubleVar, bool: BooleanVar}
Objects: Dict[str, T] = {
    "root": None
}


class ObjectVar(Variable, Generic[T]):
    """Adds support for storing objects in VariableDict objects.
    The main idea for this object is that it will allow a reference
    to the root window of the application without needing to type
    'self.master.master.master.master.title()' to access the title
    method of the main window.
    """

    def __init__(self, master, name: str, value: T):
        super().__init__(master, "", name)

        Objects[name] = value

    def get(self):
        super().get()  # cause any traces to trigger
        return Objects[self._name]

    def set(self, value: T):
        Objects[self._name] = value
        super().set("")  # cause any traces to trigger


class VariableDict(dict, Dict[str, Variable]):
    ALLOW_OVERWRITE = False
    IGNORE_TYPE_INCOMPATIBILITIES = IGNORE_TYPE_INCOMPATS = False
    ALLOW_IMPLICIT_CREATION = False  # if a key does not exist, create it?
    ALLOW_IMPLICIT_ASSIGNMENT = True  # if a value is a builtin,

    def __init__(self, name: str, master=None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.master = master
        self.name = name

    def __setitem__(self, key: str, value: Union[Variable, Any]) -> None:
        existing: Variable = self.get(key)
        if not isinstance(value, Variable):
            if existing is None:
                if self.ALLOW_IMPLICIT_CREATION:
                    meta = TYPE_MAPPING.get(type(value))
                    if meta is None:
                        if not self.IGNORE_TYPE_INCOMPATIBILITIES:
                            raise TypeError(
                                f"Type: {type(value)} is not supported."
                            )
                        else:
                            meta = Variable
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
    def from_mapping(cls, mapping: Dict[str, Any], name: str, master: Misc) -> "VariableDict":
        rdict = cls(name, master)
        for key, value in mapping.items():
            meta: Type[Variable] = TYPE_MAPPING.get(type(value), Variable)
            if meta is None:
                if not cls.IGNORE_TYPE_INCOMPATIBILITIES:
                    raise ValueError(
                        f"Type: {type(value)} is not supported."
                    )
                else:
                    meta = Variable
            rdict[key] = meta(master=master, name=f"{key}_{name}", value=value)

        return rdict

    @classmethod
    def from_existing(cls, other: "VariableDict", name: str, master: Misc=None) -> "VariableDict":
        rdict = cls(name, master)
        for key, value in other.items():
            meta: Type[Variable] = type(value)
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

            if isinstance(value, Variable):
                try:
                    self[key].set(value.get())
                except KeyError:
                    meta: Type[Variable] = type(value)
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
            ignore: Tuple[str, ...] = None, **kwargs
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

            key_reg: Tuple[str, ...] = option_regex.findall(key)
            lkey = "".join(key_reg)
            fallback = value.get()

            try:
                if isinstance(value, BooleanVar):
                    x = settings.getboolean(
                        section, lkey,
                        fallback=fallback
                    )
                elif isinstance(value, IntVar):
                    x = settings.getint(
                        section, lkey,
                        fallback=fallback
                    )
                elif isinstance(value, DoubleVar):
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
            ignore: Tuple[str, ...] = None, **kwargs
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
            if key in ignore or not isinstance(value, Variable):
                continue

            key_reg: Tuple[str, ...] = option_regex.findall(key)
            lkey = "".join(key_reg)

            config.set(section, lkey, str(value.get()))

        with open(file, "w") as config_file:
            config.write(config_file)

    def get_true(self, key) -> Union[str, float, int, bool]:
        return self[key].get()
