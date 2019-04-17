import tkinter as tk
from tkinter import ttk
from tkinter.filedialog import askdirectory, asksaveasfilename
import tkexpanded as tke
from time import time
from math import ceil
from typing import (
    List, Optional, Tuple, ClassVar,
    Dict, TypeVar, Hashable, Mapping,
)
from itertools import count
from collections import OrderedDict
import asyncio
import os
from PIL import Image
from PIL import ImageFile
from PIL.ImageTk import PhotoImage
from sizeof import total_size


ImageFile.LOAD_TRUNCATED_IMAGES = True
tk._support_default_root = 0
# tke.enable_logging(logging.DEBUG)

# ****** Type Aliases ******
_VT = TypeVar("_VT")


def resource_path(rel):
    return os.path.join(
        os.environ.get(
            "_MEIPASS2",
            os.path.abspath(".")
        ),
        rel
    )


class Animation(list, List[PhotoImage]):
    __slots__ = (
        "finished_loading", "delays", "frame_count",
        "width", "height", "canvas", "unedited"
    )
    loaders: ClassVar[int] = 5

    def __init__(self, canvas: tk.Canvas):
        super(Animation, self).__init__()

        # ****** Animation Information ******
        self.delays: List[float] = []
        self.finished_loading = False
        self.frame_count = 1

        # ****** Canvas Information ******
        # since animations have to be reloaded
        # when the canvas is resized, these
        # values can be stored here.
        self.width = canvas.winfo_width()
        self.height = canvas.winfo_height()
        self.canvas = canvas

        # ****** Unedited Gif ******
        # used for faster loading
        self.unedited: Image.Image = None

    def load(self, filename: str, rotation: int, loop: asyncio.AbstractEventLoop = None):
        if loop is None:
            loop = asyncio.get_event_loop()
        loop.create_task(self.loader(filename, rotation, loop))

    async def loader(self, filename: str, rotation: int, loop: asyncio.AbstractEventLoop):
        # ****** Load Image ******
        if self.unedited is None:
            image: Image.Image = await loop.run_in_executor(None, Image.open, filename)
            self.unedited = image
        else:
            image = self.unedited

        # ****** Aspect Ratio Work ******
        w, h = image.size
        ratio = w / h

        if w > self.width or h > self.height:
            if w >= h:
                nw, nh = self.width, ceil(self.width / ratio)

                if nh > self.height:
                    nw, nh = ceil(self.height * ratio), self.height
            else:
                nw, nh = ceil(self.height * ratio), self.height

                if nw > self.width:
                    nw, nh = self.width, ceil(self.width / ratio)
            w, h = nw, nh

        # ****** Create Frame Queue ******
        queue = asyncio.Queue()

        # ****** Create Task List ******
        tasks: List[asyncio.Task] = []

        try:
            # ****** Create Frame Loaders ******
            for i in range(self.loaders):
                task = asyncio.create_task(
                    self._load_worker(queue, w, h, rotation, loop)
                )
                tasks.append(task)

            # ****** Add Frames to Queue ******
            for i in count(0):
                if i > len(self):
                    image = await loop.run_in_executor(None, image.convert, "RGBA")
                    queue.put_nowait((image, i))

                try:
                    await loop.run_in_executor(None, image.seek, i + 1)
                except EOFError:
                    break

                self.frame_count += 1

                await asyncio.sleep(0)

            # Wait for queue to finish
            await queue.join()
        except asyncio.CancelledError:
            raise
        finally:
            # Cancel running frame loaders
            for task in tasks:
                task.cancel()
                await asyncio.sleep(0)

            # Give the tasks time to cancel
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _load_worker(
            self, queue: asyncio.Queue, w: int, h: int, r: int,
            loop: asyncio.AbstractEventLoop
    ):
        # run the worker until cancelled
        while True:
            # get the frame from the queue
            frame, i = await queue.get()

            # put the frame time into the delays list
            self.delays.append(frame.info["duration"] / 1000)

            # rotate the frame
            if r != 0:
                frame = await loop.run_in_executor(
                    None, lambda: frame.rotate(-90 * r, expand=1)
                )

            # resize the frame to fit within the canvas
            frame = await loop.run_in_executor(
                None, lambda: frame.resize((w, h), Image.BILINEAR)
            )

            # convert the frame to the tkinter format
            photoimage = PhotoImage(
                image=frame, master=self.canvas,
                format=f"gif -index {i}"
            )

            # add the frame to the animation
            self.append(photoimage)

            # mark the task as finished
            queue.task_done()

            # suspend
            await asyncio.sleep(0)


class Cache(OrderedDict, Dict[Hashable, _VT]):
    """"""

    __slots__ = ("max_size", "default_factory")

    def __init__(self, max_size: int, default_factory: type = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_size = max_size
        self.default_factory = default_factory

    def _cull(self):

        if total_size(self) > self.max_size and len(self) > 1:
            oldest = next(iter(self))
            del self[oldest]

    def __setitem__(self, key: Hashable, value: _VT):
        super().__setitem__(key, value)
        self._cull()

    def __getitem__(self, key: Hashable):
        try:
            value = super().__getitem__(key)
            self.move_to_end(key)
        except KeyError:
            if self.default_factory is None:
                raise
            else:
                value = self.default_factory()
                self[key] = value

        self._cull()

        return value

    def update(self, __m: Mapping[Hashable, _VT], **kwargs: _VT):
        super().update(__m, **kwargs)
        self._cull()


class AskYesNo(tk.Toplevel):
    def __init__(self, master, message="", title=""):
        super(AskYesNo, self).__init__(master=master)
        self.toggle()
        self.update()
        self.master = master
        self.prev = self.focus_get()

        # ****** Window Setup ******
        # self.lift()
        # self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self.return_no)
        self.configure(background="#293134")
        self.bind("<FocusOut>", self.take_focus)
        self.title(title)
        self.response = False

        # ****** Window Contents ******
        cont = ttk.Frame(self)
        cont.pack(padx=5, pady=5)

        label = tk.Message(cont, text=message, width=200, background="#293134", foreground="#E0E2E4")
        label.pack(side="top", fill="x")

        # yes button
        yes = ttk.Button(cont, text="Yes", command=self.return_yes)
        yes.bind("<Return>", self.return_yes)
        yes.pack(side="left", padx=5, pady=2)
        yes.focus_set()

        # no button
        no = ttk.Button(cont, text="No", command=self.return_no)
        no.bind("<Return>", self.return_no)
        self.bind_all("<Escape>", self.return_no)
        no.pack(side="right", padx=5, pady=2)

        # bind left and right
        no.bind("<Left>", lambda e: yes.focus_set())
        no.bind("<Right>", lambda e: yes.focus_set())
        yes.bind("<Right>", lambda e: no.focus_set())
        yes.bind("<Left>", lambda e: no.focus_set())

        # ****** Show Window ******
        self.center()
        self.overrideredirect(True)
        # self.transient(master._root())
        self.toggle()
        self.grab_set()
        self.update()

        self.wait_window(self)
        self.update()

    def take_focus(self, event=None):
        self.center()
        self.lift()

    def return_yes(self, event=None):
        self.response = True
        self.grab_release()
        self.prev.focus_set()
        self.destroy()

    def return_no(self, event=None):
        self.response = False
        self.grab_release()
        self.prev.focus_set()
        self.destroy()

    def center(self):
        self.update_idletasks()
        width: int = self.winfo_width()
        height: int = self.winfo_height()

        root = self.master._root()
        x = root.winfo_x() + (root.winfo_width() // 2 - width // 2)
        y = root.winfo_y() + (root.winfo_height() // 2 - height // 2)
        string = '{}x{}+{}+{}'.format(width, height, x, y)
        self.geometry(string)

    def toggle(self):
        self.attributes("-alpha", float(not self.attributes("-alpha")))


def askyesno(master, message: str = "", title: str = "", ) -> bool:
    """Highly blocking."""
    dialog = AskYesNo(master, message, title)
    return dialog.response


class ImageViewerApp(tke.ApplicationBase):
    globals = {
        "source": ""
    }

    def __init__(self, loop):
        super(ImageViewerApp, self).__init__(
            loop, title="Images", icon="ImageViewer.ico"
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

        settings = tke.VariableDict.from_mapping(self.globals, "globals", self)

        self.pages = tke.PageMaster(self)
        self.pages.pack(expand=True, fill="both")

        # ****** Register Pages ******
        self.pages.page_register(
            ImageContainer, "container", 1, 0, loop, settings,
            highlight=blue_grey, background=blue_grey
            # highlight="white", background="white"
        )
        # self.pages.page_register(
        #     SelectionPage, "selection", 0, 0, settings
        # )
        self.pages.page_register(
            SelectionPage, "selection", 2, 0, settings
        )

        # ****** Configure Pages ******
        self.pages.rowconfigure(0, weight=0)
        self.pages.rowconfigure(2, weight=0)
        self.pages["selection"].rowconfigure(0, weight=0)

        # ****** Show Pages ******
        self.pages.page_show("container", columnspan=3)
        self.pages.page_show("selection")


class ImageContainer(tke.PageBase):
    """Page that displays images in a canvas.

    Relies on the following variables to be
    defined in a VariableDict object:
     -> source

    """

    def __init__(
            self, master: tke.PageMaster, loop: asyncio.AbstractEventLoop,
            settings: tke.VariableDict, width=500, height=500, highlight=None,
            background="white", **kwargs
    ):
        """Base Constructor. Should not have to be rewritten by subclasses."""
        super(ImageContainer, self).__init__(master, **kwargs)

        # TODO: Implement Scrollwheel Zoom
        # TODO: Finish implementing Delete key functionality

        # ****** Assign Parameters ******
        self.settings = settings
        self.height = height
        self.width = width
        self.loop = loop

        # ****** Create Canvas ******
        self.canvas = canvas = tk.Canvas(
            self, width=self.width,
            height=self.height,
            bg=background,
            highlightbackground=highlight,
            highlightcolor=highlight
        )

        # ****** Assign Attributes ******
        self.switch_speed = 0.14  # seconds
        self.last_switch = time()  # seconds

        self.current_index = 0
        self.current_rotation = 0
        self.current_zoom = 1

        self.play_tasks: Dict[str, asyncio.Task] = {}
        self.loading_task: asyncio.Task = None

        self.current_image: PhotoImage = None
        self.current_image_edited: Image.Image = None
        self.current_image_unedited: Image.Image = None

        self.images: List[str] = []
        cache_size = pow(2, 17)  # allow cache to grow to at most 1GiB
        self.gif_cache: Cache[Animation] = Cache(cache_size)
        self.use_gif_for_loading = False
        self.loading_gif: Animation = None
        loading_gif_name = "Loading.gif"
        if os.path.exists(resource_path(loading_gif_name)):
            self.use_gif_for_loading = True
            cache = Animation(canvas)
            cache.load(
                resource_path(loading_gif_name),
                0, self.loop
            )
            self.loading_gif = cache

        self.configuring = False
        self.last_configure = time()

        source_var: tk.Variable = settings["source"]
        source_var.trace_add("write", self.update_source)
        self.current_source = source_var.get()

        # ****** Configuring ******
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        # ****** Grid the Canvas ******
        canvas.grid(row=0, column=0, sticky="nsew")
        canvas.focus_set()

        # ****** Create Keybindings ******
        canvas.bind("a", self.handle_switch)
        canvas.bind("d", self.handle_switch)
        canvas.bind("<Left>", self.handle_switch)
        canvas.bind("<Right>", self.handle_switch)
        canvas.bind("<MouseWheel>", self.handle_switch)

        canvas.bind("<Button-1>", self.handle_clicks)
        canvas.bind("<Configure>", self.handle_resize)
        canvas.bind("<Delete>", self.handle_delete)

        canvas.bind("<Control-e>", self.handle_rotate)
        canvas.bind("<Control-q>", self.handle_rotate)
        canvas.bind("<Control-S>", self.handle_save)

        # ****** Gif Progressbar ******
        self.progress_bar = progress = ttk.Progressbar(
            self, maximum=1500, value=0
        )
        progress.grid(row=1, column=0, sticky="ew")
        progress.grid_remove()

        # ****** Separator ******
        separator = ttk.Separator(self)
        separator.grid(row=2, column=0, sticky="ew")

        # ****** Load First Images ******
        self.images = self.load_images(self.current_source)

    def reload_context(self):
        if self.play_tasks is not None:
            for task in self.play_tasks.values():
                task.cancel()
            self.play_tasks.clear()
            self.progress_bar.grid_remove()
            self.progress_bar.config(value=0)
        self.current_rotation = 0
        self.current_zoom = 0

    def handle_resize(self, event=None):
        """Internal Function. Does not have to be rewritten
        by subclasses."""
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        safe_bound = self.progress_bar.winfo_height() * 2
        # safe_bound = 25
        if self.width == w and self.height - safe_bound < h < self.height + safe_bound:
            return
        self.width = w
        self.height = h
        self.last_configure = time()
        self.after_idle(self.handle_resize_end)

    def handle_resize_end(self):
        """Internal Function. Does not have to be rewritten
        by subclasses."""
        if time() - self.last_configure > 0.100:
            self.gif_cache.clear()
            self.reload_context()
            self.show(self.current_index, self.current_index, self.current_rotation)
            self.configuring = False
        else:
            self.after_idle(self.handle_resize_end)

    def handle_delete(self, event):
        """Internal Function. Does not have to be rewritten
        by subclasses."""
        response = askyesno(self, "Delete this?")
        if not response:
            return
        self.remove_image(self.get_image_path(self.current_index))
        self.canvas.delete("text")
        self.images.pop(self.current_index)

        def func():
            self.show(self.current_index)  # the new item will take it's place.

        self.after(100, func)

    def remove_image(self, path: str):
        """Internal Function. Has to be rewritten by subclasses."""
        os.remove(path)

    def handle_rotate(self, event):
        if not self.switch_elapsed():
            return

        if event.keysym == "q":
            new_rot = self.current_rotation - 1
            if new_rot == -4:
                new_rot = 0
        else:
            new_rot = self.current_rotation + 1
            if new_rot == 4:
                new_rot = 0
        self.show(self.current_index, self.current_index, new_rot)
        self.current_rotation = new_rot

    def handle_switch(self, event=None, key_override: Optional[str] = None):
        """Show the next image in the list. Does not have to be
        rewritten by subclasses."""
        if not self.switch_elapsed():
            return

        def next_image():
            if self.current_index < len(self.images) - 1:
                new_index = self.current_index + 1
                self.reload_context()

                self.show(self.current_index, new_index)
                self.current_index = new_index
            else:
                self.show(self.current_index, self.current_index)

        def prev_image():
            if self.current_index > 0:
                new_index = self.current_index - 1
                self.reload_context()

                self.show(self.current_index, new_index)
                self.current_index = new_index
                self.current_rotation = 0
                self.current_zoom = 0
            else:
                self.show(self.current_index, self.current_index)

        if key_override or event.type == tk.EventType.Key:
            key = key_override or event.keysym

            if key in ("d", "Right"):
                next_image()
            elif key in ("a", "Left"):
                prev_image()

        elif event.type == tk.EventType.MouseWheel:
            delta = event.delta

            if delta > 0:
                next_image()
            else:
                prev_image()

    def handle_clicks(self, event):
        """Internal Function. Handles user click events.
        Does not have to be rewritten by subclasses."""
        # shorthands
        # widget = self.focus_get()
        canvas = self.canvas

        # if widget is canvas:  Here to remember how to do it.
        x = canvas.canvasx(event.x)
        y = canvas.canvasy(event.y)

        if 0 < x <= self.width // 8 and 0 < y < self.height:
            self.handle_switch(key_override="Left")
        elif self.width > x >= self.width - self.width // 8 and 0 < y < self.height:
            self.handle_switch(key_override="Right")
        canvas.focus_set()

    def handle_save(self, event=None):
        path = self.get_image_path(self.current_index)
        name = os.path.split(path)[1]
        ext = os.path.splitext(name)[1]
        new_path = asksaveasfilename(
            master=self, filetypes=((ext[1:] + " files", "*"+ext), ("all files", "*.*")),
            initialdir=self.current_source
        )
        if new_path == "":
            return

        if os.path.splitext(new_path)[1] == "":
            new_path += ext

        self.current_image_edited.save(new_path)

        # can't do this because we have no way of knowing the new current_index value
        # if os.path.split(new_path) == self.current_source:
        #     self.images = self.load_images(new_path)

    def is_good_source(self, source: str) -> bool:
        """Internal Function. Has to be rewritten by subclasses."""
        return os.path.isdir(source)

    def update_source(self, *args):
        """Internal Function. Does not have to be rewritten
        by subclasses."""
        value = self.settings.get_true("source")

        # if I'm clicking "load", I don't care
        # if it's the same directory.
        # if value == self.current_source:
        #     return

        if self.is_good_source(value):
            images = self.load_images(value)
            # if len(images) > 0:
            self.images = images
            if value != self.current_source:
                self.gif_cache.clear()
                self.reload_context()
                self.current_index = 0
                self.current_image_unedited = None
            self.current_source = value
            self.show(self.current_index, self.current_index, self.current_rotation)

    def load_images(self, folder: str) -> List[str]:
        """Loads the list of images. Has to be rewritten by subclasses"""
        def func(name):
            if os.path.isdir(name):
                return False

            if os.path.splitext(name)[1] not in (".jpg", ".png", ".jpeg", ".gif", ".ico"):
                return False

            return True

        return list(filter(func, os.listdir(os.path.abspath(folder))))

    def switch_elapsed(self) -> bool:
        """Internal Function. Check whether the minimum time threshold
        has passed before switching images. Performance Implement.
        Does not have to be rewritten by subclasses."""
        new_switch = time()
        if self.last_switch > new_switch - self.switch_speed:
            return False
        else:
            self.last_switch = new_switch
            return True

    def get_image_path(self, index: int) -> Optional[str]:
        """Internal Function. Get Full Image Path for Show Function.
        Has to be rewritten by subclasses."""
        try:
            return os.path.join(self.current_source, self.images[index])
        except IndexError:
            return None

    def update_title(self, name: str, res: Tuple[int, int] = (None, None)):
        root: tk.Tk = self._root()
        if root.winfo_width() < len(name) + 600:
            name = os.path.split(name)[-1]
        if None not in res:
            root.title(f"Images - {name} ({', '.join(map(str, res))})")
        else:
            root.title(f"Images - {name}")

    async def show_regular(self, image, name, rotate):
        # ****** Rotate Image ******
        if rotate != 0:
            image: Image.Image = image.rotate(-90 * rotate, expand=1)  # .resize((h, w), Image.BICUBIC)
        self.current_image_edited = image

        # ****** Get Dimensions ******
        w, h = image.size
        self.update_title(name, (w, h))
        ratio = w / h

        # ****** Resize Images to Fit Canvas ******
        if w > self.width or h > self.height:
            # ****** Fix Aspect Ratio ******
            if w >= h:
                nw, nh = self.width, (ceil(self.width / ratio))

                if nh > self.height:
                    nw, nh = (ceil(self.height * ratio)), self.height
            else:
                nw, nh = (ceil(self.height * ratio)), self.height

                if nw > self.width:
                    nw, nh = self.width, (ceil(self.width / ratio))

            # ****** Resize Image ******
            image: Image.Image = image.resize((nw, nh), Image.BICUBIC)
            # w, h = nw, nh

        photoimage = PhotoImage(image, master=self.canvas)

        # ****** Display Image ******
        self.canvas_show_image(photoimage)

    async def frame_loader(self, queue, cache, w, h, rotate):
        # there might be 5 of these running at once.

        while True:
            frame, i = await queue.get()

            if rotate != 0:
                frame = await self.loop.run_in_executor(
                    None, lambda: frame.rotate(-90 * rotate, expand=1)
                )

            frame = await self.loop.run_in_executor(
                None, lambda: frame.resize((w, h), Image.BILINEAR)
            )

            photoimage = PhotoImage(
                image=frame, master=self.canvas,
                format=f"gif -index {i}"
            )

            # self.gif_cache[name].append(
            #     photoimage
            # )
            # cache[i] = photoimage
            cache.append(photoimage)
            self.progress_bar.step()
            queue.task_done()
            await asyncio.sleep(0)

    async def load_gif(self, image, cache, name, rotate) -> Animation:
        """Perhaps these should return an object to pass to a show function?"""

        tkimage = image.convert("RGBA")
        w, h = tkimage.size
        self.update_title(name, (w, h))
        ratio = w / h

        if w > self.width or h > self.height:
            if w >= h:
                nw, nh = self.width, ceil(self.width / ratio)

                if nh > self.height:
                    nw, nh = ceil(self.height * ratio), self.height
            else:
                nw, nh = ceil(self.height * ratio), self.height

                if nw > self.width:
                    nw, nh = self.width, ceil(self.width / ratio)
            w, h = nw, nh

        frame_queue = asyncio.Queue()
        total_frames = 0

        # core: Dict[int, PhotoImage] = {}

        tasks: List[asyncio.Task] = []
        try:

            if not self.use_gif_for_loading:
                self.progress_bar.grid()
            else:
                loading_task = self.loop.create_task(
                    self.repeat_gif(self.loading_gif, self.loading_gif_delay)
                )

            for i in range(25):
                # load frames
                task = asyncio.create_task(
                    self.frame_loader(frame_queue, cache, w, h, rotate)
                )
                tasks.append(task)

            # grab the frames from the gif
            # we need this to run side by side with the frame loaders.
            for i in count(0):
                if i >= len(cache):
                    tkimage = await self.loop.run_in_executor(None, lambda: image.convert("RGBA"))
                    frame_queue.put_nowait((tkimage, i))
                    total_frames += 1

                try:
                    await self.loop.run_in_executor(None, image.seek, i + 1)
                except EOFError:
                    break

                await asyncio.sleep(0)

            await frame_queue.join()
        except asyncio.CancelledError:
            raise
        finally:
            for task in tasks:
                task.cancel()
                await asyncio.sleep(0)
            await asyncio.gather(*tasks, return_exceptions=True)

            if not self.use_gif_for_loading:
                self.progress_bar["value"] = self.progress_bar["maximum"]
                self.progress_bar.grid_remove()
            else:
                loading_task.cancel()
                # await asyncio.gather(loading_task)

        # gif cache culling

        return cache

    async def show_gif(self, image, name, delay, rotate):
        cache = self.gif_cache[name]
        if cache.finished_loading:
            frames = cache
        else:
            frames = await self.load_gif(image, cache, name, rotate)
            self.gif_cache[name].finished_loading = True
        await self.repeat_gif(frames, delay)

    async def show_gif_concurrent(self, image, name, rotate):
        cache = self.gif_cache[name]

        tkimage = image.convert("RGBA")
        w, h = tkimage.size
        self.update_title(name, (w, h))
        ratio = w / h

        if w > self.width or h > self.height:
            if w >= h:
                nw, nh = self.width, ceil(self.width / ratio)

                if nh > self.height:
                    nw, nh = ceil(self.height * ratio), self.height
            else:
                nw, nh = ceil(self.height * ratio), self.height

                if nw > self.width:
                    nw, nh = self.width, ceil(self.width / ratio)
            w, h = nw, nh

        for i in count(0):
            if i >= len(cache):
                if rotate != 0:
                    tkimage = tkimage.rotate(-90 * rotate, expand=1)
                    # await asyncio.sleep(0)
                if i == 0:
                    self.current_image_edited = tkimage

                tkimage = tkimage.resize((w, h), Image.BILINEAR)
                # await asyncio.sleep(0)

                photoimage = PhotoImage(
                    image=tkimage, master=self.canvas,
                    format=f"gif -index {i}"
                )
                cache.append(
                    photoimage
                )
                await asyncio.sleep(0)

            try:
                image.seek(i + 1)
            except EOFError:
                self.gif_cache[name].finished_loading = True
                break

            tkimage = await self.loop.run_in_executor(None, image.convert, "RGBA")
            await asyncio.sleep(0)

    def show(self, cur_index: int = 0, index: int = 0, rotate: int = 0):
        """Show the image at the given index.
        Does not have to be overwritten in subclasses."""
        imgname = self.get_image_path(index)

        if index != cur_index or self.current_image_unedited is None:
            if imgname is None:
                self.canvas.delete("text")
                return

            try:
                image = Image.open(imgname)
                self.current_image_unedited = image
            except FileNotFoundError:
                return
        else:
            image = self.current_image_unedited

        self.canvas.delete("text")
        self.update_title(imgname)
        if os.path.splitext(imgname)[1] in (".gif", ):
            if len(self.play_tasks):
                tasks = self.play_tasks.values()
                for task in tasks:
                    task.cancel()

            try:
                delay = image.info["duration"] / 1000
            except KeyError:
                delay = 1 / 15

            # on-the-fly loading:
            # cache = self.gif_cache[imgname]
            # if not self.gif_cache_is_finished[imgname]:
            #     task = self.load_gif(image, imgname, rotate)
            #     self.play_tasks["load_frames"] = self.loop.create_task(task)
            # task = self.repeat_gif(cache, delay)
            # self.play_tasks["show_gif"] = self.loop.create_task(task)

            # progress-bar loading:
            task = self.show_gif(image, imgname, delay, rotate)
            self.play_tasks["load_gif"] = self.loop.create_task(task)
        else:
            if len(self.play_tasks):
                tasks = self.play_tasks.values()
                for task in tasks:
                    task.cancel()
            task: asyncio.Task = self.show_regular(image, imgname, rotate)
            self.play_tasks["show_regular"] = self.loop.create_task(task)

    def canvas_show_image(self, image: PhotoImage):
        self.current_image = image
        # self.canvas.itemconfig("text", image=image)
        self.canvas.delete("text")
        self.canvas.create_image(
            self.width // 2, self.height // 2,
            image=image, tag="text"
        )
        self.update_idletasks()

    async def repeat_gif(self, frames: List[PhotoImage], delay: float = 1/30):
        while True:
            for frame in frames:
                self.canvas_show_image(frame)
                await asyncio.sleep(delay)
            await asyncio.sleep(0)

    async def play_animation(self, animation: Animation):
        while True:
            for i in range(animation.frame_count):
                self.canvas_show_image(animation[i])
                await asyncio.sleep(animation.delays[i])
            await asyncio.sleep(0)


class SelectionPage(tke.PageBase):
    def __init__(self, master: tke.PageMaster, settings: tke.VariableDict, **kwargs):
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
        source = self.source.get()
        self.settings.get("source").set(source)

    def browse(self, event=None):
        back = self.source.get()
        source = askdirectory(master=self, title="Select Folder")
        if source in ("", back):
            return

        self.source.set(source)


if __name__ == '__main__':
    app = ImageViewerApp(asyncio.get_event_loop())
    app.run()
