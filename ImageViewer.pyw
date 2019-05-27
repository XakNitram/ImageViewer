import tkinter as tk
from tkinter import ttk
from tkinter.filedialog import askdirectory
import tkexpanded as tke
from tkexpanded.variables import ObjectVar, VariableDict
from image_container import ImageContainer
import asyncio
import os


tk._support_default_root = 0
tke.enable_logging(2)


def resource_path(rel):
    return os.path.join(
        os.environ.get(
            "_MEIPASS2",
            os.path.abspath(".")
        ),
        rel
    )


class ImageViewerApp(tke.SimpleApplication):
    globals = {
        "source": "",
        "reource_path": resource_path("")
    }

    def __init__(self, loop):
        super(ImageViewerApp, self).__init__(
            loop=loop, title="Images", icon="ImageViewer.ico"
        )

        # self.resizable(False, False)

        # keep these to know that they exist.
        # self.overrideredirect(True)
        # self.geometry("+250+250")
        # self.lift()
        # self.wm_attributes("-topmost", True)
        # self.wm_attributes("-disabled", True)

        # set an unused color as the marker for transparency
        # self.wm_attributes("-transparentcolor", "#012345")

        style = ttk.Style(master=self)
        blue_grey = "#293134"
        style.configure("TFrame", background=blue_grey)
        style.configure("TLabel", background=blue_grey, foreground="#E0E2E4")
        style.configure("TEntry", background=blue_grey)
        style.configure("TButton", background=blue_grey)
        style.configure("TSeparator", background=blue_grey)
        # style.theme_use("clam")

        settings = VariableDict.from_mapping(self.globals, "globals", self)
        settings["root"]: ObjectVar[tk.Tk] = ObjectVar(self, "root", self)

        self.pages = tke.PageMaster(self)
        self.pages.pack(expand=True, fill="both")

        # ****** Register Pages ******
        self.pages.register(
            ImageContainer, "container", 1, 0, loop, settings,
            highlight=blue_grey, background=blue_grey
            # highlight="white", background="white"
        )
        # self.pages.page_register(
        #     SelectionPage, "selection", 0, 0, settings
        # )
        self.pages.register(
            SelectionPage, "selection", 2, 0, settings
        )

        # ****** Configure Pages ******
        self.pages.rowconfigure(0, weight=0)
        self.pages.rowconfigure(2, weight=0)
        self.pages["selection"].rowconfigure(0, weight=0)

        # ****** Show Pages ******
        self.pages.show("container", columnspan=3)
        self.pages.show("selection")


# simple selection page
class SelectionPage(tke.SimplePage):
    def __init__(self, master: tke.PageMaster, settings: VariableDict, **kwargs):
        super(SelectionPage, self).__init__(master, **kwargs)

        self.settings = settings

        lf = tke.LabelFrame(self)
        lf.pack(expand=False, fill="x", padx=10, pady=20)
        label, frame = lf.add_label("Folder")

        init_source = settings.get_true("source")
        self.source = fe_var = tk.StringVar(master=self, value=init_source, name="selection_source")
        fe = ttk.Entry(frame, textvariable=fe_var)
        fe.pack(fill="x", expand=True, side="left")

        fb = ttk.Button(frame, text="Browse", command=self.browse)
        fb.pack(side="right", padx=5)

        fl = ttk.Button(frame, text="Load", command=self.set_source)
        fl.pack(side="right", padx=5)

    def set_source(self, event=None):
        # source = self.source.get()
        # self.settings.get("source").set(source)

        source = self.source.get()
        self.master.message(
            "container", "<<UpdateSource>>",
            source
        )

    def browse(self, event=None):
        back = self.source.get()
        source = askdirectory(master=self, title="Select Folder")
        if source in ("", back):
            return

        self.source.set(source)


if __name__ == '__main__':
    ImageViewerApp(asyncio.get_event_loop()).run()
