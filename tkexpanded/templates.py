# ****** Tkinter Imports ******
import tkinter as tk
from tkinter import ttk
import tkexpanded as tke
from tkinter.font import families

# ****** Utility Imports ******
import typing as tp

# ****** Operational Imports ******
import asyncio

__all__ = ("DebugPage", )


class DebugPage(tke.PageBase):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)

        self.rowconfigure(0, weight=1)
        output = tke.Output(
            self, relief="sunken",
            width=40, height=1,
            bg="#E6E6E6", fg="#293134",
            selectforeground="#293134",
            selectbackground="#808080",
            takefocus=False
        )

        if "Source Code Pro" in families(root=master):
            output["font"] = ("Source Code Pro", "10")
        output.grid(
            row=0, column=0,
            sticky="nsew",
            padx=1, pady=1
        )
        tke.Streams["debug"] = output

    def exit(self):
        pass

    def enter(self):
        pass


class OptionsPage(tke.PageBase):
    def __init__(
            self, master: tke.PageMaster, loop: asyncio.AbstractEventLoop,
            settings: tke.VariableDict=None, *args, **kwargs
    ):
        # ****** Non-standard Attributes ******
        # These attributes may be overwritten by subclasses of PageBase
        self.settings = settings

        # ****** Inherit from Parents ******
        super().__init__(master, **kwargs)

        # ****** Page Variables ******
        self.loop = loop
        self.jobs: tp.Dict[str, asyncio.Future] = {}
        self._settings_changed = False

        # ****** Settings Dictionary Work ******
        self.local_vars = tke.VariableDict.from_existing(self.settings, name="optn", master=self)

        # ****** Main Options Frame ******
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=9)
        # self.frame.rowconfigure(2, weight=1)

        # ****** Mainframe Bindings ******
        # self.bind_all("Control-s", self.config_apply)

        # ****** Description Notebook ******
        notebook_frame = ttk.Frame(self)
        notebook_frame.grid(
            row=1, column=0,
            sticky="nsew",
            padx=5
        )
        notebook_frame.rowconfigure(0, weight=1)
        notebook_frame.columnconfigure(0, weight=1)

        notebook = tke.PaddedNotebook(notebook_frame)
        notebook.grid(sticky="nsew")
        self.notebook = notebook

        buttons_left = {}
        buttons_right = {
            "OK": self.ok_button_func,
            "Apply": self.apply_button_func,
            "Cancel": self.cancel_button_func
        }
        buttons = tke.ButtonFrame(self)
        buttons.make_buttons(buttons_left, buttons_right)
        apply_button = buttons.right["Apply"]
        apply_button.configure(state="disabled")
        buttons.grid(row=2, sticky="sew", padx=5, pady=5)
        self.buttons = buttons

        def widget_state(v: bool) -> None:
            apply_button.configure(state="normal" if v else "disabled")
        self.widget_state = widget_state

    def enter(self):
        self.widget_state(False)
        self.jobs["check"] = asyncio.ensure_future(self.change_check(), loop=self.loop)
        self.local_vars.update(self.settings)

    def exit(self):
        self.jobs["check"].cancel()
        self.local_vars.update(self.settings)

    async def change_check(self):
        while True:
            diff = False
            for var, back in zip(self.local_vars.values(), self.settings.values()):
                if var.get() != back.get():
                    diff = True
                    break
                await asyncio.sleep(0)

            already = not (diff ^ self._settings_changed)
            if not already:
                if diff:
                    self.widget_state(True)
                else:
                    self.widget_state(False)
            self._settings_changed = diff
            await asyncio.sleep(0.063)

    def cancel_button_func(self):
        pass

    def apply_button_func(self):
        self.settings.update(self.local_vars)

    def ok_button_func(self):
        self.settings.update(self.local_vars)
