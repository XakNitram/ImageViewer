# ****** stdlib imports ******
from typing import (
    List, Dict, Union,
    Optional, Tuple
)
from functools import partial
from itertools import count
from math import ceil
from time import time
import asyncio
import os

# ****** non-stdlib imports ******
from cache import Cache
from PIL import Image
from PIL import ImageFile
from PIL.ImageTk import PhotoImage
import tkexpanded as tke
from tkexpanded.variables import VariableDict
from tkinter.filedialog import asksaveasfilename
from tkinter import ttk
import tkinter as tk
from animation import Animation, Static

ImageFile.LOAD_TRUNCATED_IMAGES = True


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


class ImageContainer(tke.PageBase):
    """Page that displays images in a canvas.
    Implements some default functionality.

    Relies on the following variables to be
    defined in a VariableDict object:
     -> resource_path => defaults to ''
     -> loading_image => defaults to 'Loading.gif'
     -> source        => defaults to ''

    """

    def __init__(
            self, master: tke.PageMaster, loop: asyncio.AbstractEventLoop,
            settings: VariableDict, width=500, height=500, highlight=None,
            background="white", **kwargs
    ):
        """Base Constructor. Should not have to be rewritten by subclasses."""
        super(ImageContainer, self).__init__(master, **kwargs)

        # TODO: Implement Scrollwheel Zoom
        # TODO: Finish implementing Delete key functionality

        # ****** Assign Parameters ******
        self.settings = settings
        self.root: tk.Tk = settings.get_true("root")

        self.resource_path = settings.get_true(
            "resource_path", ""
        )

        self.loading_gif_name = settings.get_true(
            "loading_image", ""
        )

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

        # tkinter will not display the image without a stored
        # reference to it somewhere else in the program
        self.image_reference: Image.Image = None

        self.current_image: Union[Static, Animation] = None
        self.current_image_edited: Image.Image = None
        self.current_image_unedited: Union[Static, Animation] = None

        # list of image names to load
        self.images: List[str] = []

        # cache of gifs to avoid loading the same gif over again.
        cache_size = pow(2, 17)  # allow cache to grow to at most 1GiB
        self.gif_cache: Cache[Animation] = Cache(cache_size)

        # load the gif used to give something for the user
        # to look at when loading gifs.
        self.use_gif_for_loading = False
        self.loading_gif: Animation = None

        # get the absolute path of the loading image
        loading_gif_name = os.path.join(
            self.resource_path,
            self.loading_gif_name
        )

        # determine whether the loading gif exists.
        if os.path.exists(loading_gif_name):
            self.use_gif_for_loading = True
            cache = Animation(canvas)
            cache.start_load(
                loading_gif_name,
                0, self.loop
            )
            self.loading_gif = cache

        # deal with the user resizing the window
        self.configuring = False
        self.last_configure = time()

        # allow other pages to update the source
        self.command_add("<<UpdateSource>>", self.update_source)
        self.current_source = settings.get_true("source")

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
        self.after_idle(self._resize_end)

    def _resize_end(self):
        """Internal Function. Does not have to be rewritten
        by subclasses."""
        if time() - self.last_configure > 0.100:
            self.gif_cache.clear()
            self.reload_context()
            self.show(self.current_index, self.current_index, self.current_rotation)
            self.configuring = False
        else:
            self.after_idle(self._resize_end)

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

    def update_source(self, path: str):
        """Internal Function. Does not have to be rewritten
        by subclasses."""
        self.settings["source"].set(path)
        self.root.title("Images")

        # if I'm clicking "load", I don't care
        # if it's the same directory.
        # if value == self.current_source:
        #     return

        if self.is_good_source(path):
            images = self.load_images(path)
            # if len(images) > 0:
            self.images = images
            if path != self.current_source:
                self.gif_cache.clear()
                self.reload_context()
                self.current_index = 0
                self.current_image_unedited = None
            self.current_source = path
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
                    None, partial(frame.rotate, -90 * rotate, expand=1)
                )

            frame = await self.loop.run_in_executor(
                None, partial(frame.resize, (w, h), Image.BICUBIC)
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

        tasks: List[asyncio.Task] = []
        try:

            if not self.use_gif_for_loading:
                self.progress_bar.grid()
            else:
                loading_task = self.loop.create_task(
                    self.play_animation(self.loading_gif)
                )

            for i in range(5):
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

        return cache

    async def show_gif(self, image, name, delay, rotate):
        cache = self.gif_cache.get(name)
        if cache is None:
            cache = Animation(self.canvas)
            self.gif_cache[name] = cache

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
        self.image_reference = image
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

    async def new_show(self, index: int = 0, rotate: int = 0):
        name = self.get_image_path(index)

        is_current = index == self.current_index
        has_changed = self.current_image_unedited is None

        if not is_current or has_changed:
            if name is None:
                self.canvas.delete("text")
                return

            try:
                image = Image.open(name)
                self.current_image_unedited = image
            except FileNotFoundError:
                return
        else:
            # this no longer works with the animation system
            image = self.current_image_unedited

    async def play_animation(self, animation: Animation):
        while True:
            for frame, delay in zip(animation, animation.delays):
                self.canvas_show_image(frame)
                await asyncio.sleep(delay)
            await asyncio.sleep(0)
