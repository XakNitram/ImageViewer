"""
Provides an asynchronous system for handling
the loading of PhotoImage types for
the ImageContainer system.

Proposed method for interacting with class:
can = Canvas()
var = Static(can)
var.rotate(90)

The current system is not open to subclassing.
Subclasses would have to rewrite the load function
on both systems to add new functionality.

"""

from typing import List, ClassVar
import asyncio

from PIL.ImageTk import PhotoImage
from PIL import Image
import tkinter as tk
from math import ceil
from itertools import count
from functools import partial


class Static:
    __slots__ = (
        "canvas", "image", "loaded",
        "height", "width", "rotation",
        "unedited", "_load_task"
    )

    def __init__(self, canvas: tk.Canvas):
        super().__init__()

        # tkinter's PhotoImage requires a reference
        # to a master widget.
        self.canvas = canvas

        self.image: PhotoImage = None
        self.loaded = False

        # ****** Image Manipulation Settings ******
        self.height = canvas.winfo_height()
        self.width = canvas.winfo_width()
        self.rotation = 0

        # ****** Unedited Image ******
        self.unedited: Image.Image = None

        # ****** Asyncio System ******
        self._load_task: asyncio.Task = None

    def __repr__(self):
        return "Image: w={} h={} r={}" + chr(176) + " loaded={}".format(
            self.width, self.height, self.rotation, self.loaded
        )

    def rotate(self, rotation: int):
        self.rotation += rotation

        while rotation >= 360:
            rotation -= 360

    def resize(self, width=None, height=None):
        if width is not None:
            self.width = width

        if height is not None:
            self.height = height

    def reload(self):
        """Reload the instance attributes and
        unload the image. Must be done before
        changing the """

        load_task = self._load_task
        if load_task is not None and not load_task.done():
            load_task.cancel()
        self._load_task = None

        # ****** Reload Image Manipulation Settings ******
        self.width = self.canvas.winfo_width()
        self.height = self.canvas.winfo_height()
        self.rotation = 0

        self.image = None
        self.loaded = False

    def start_load(self, filename: str, loop: asyncio.AbstractEventLoop = None):
        if loop is None:
            loop = asyncio.get_event_loop()
        loop.create_task(self.load(filename, loop))

    async def load(self, filename: str, loop: asyncio.AbstractEventLoop):
        # ****** Load Image ******
        if self.unedited is None:
            image: Image.Image = await loop.run_in_executor(None, partial(Image.open, filename))
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

        # rotate the frame
        if self.rotation != 0:
            image = await loop.run_in_executor(
                None, partial(image.rotate, -90 * self.rotation, expand=1)
            )

        # resize the frame to fit within the canvas
        image = await loop.run_in_executor(
            None, partial(image.resize, (w, h), Image.BICUBIC)
        )

        # convert the frame to the tkinter format
        self.image = PhotoImage(
            image=image, master=self.canvas
        )


class Animation(list, List[PhotoImage]):
    __slots__ = (
        "loaded", "delays", "frame_count", "rotation",
        "width", "height", "canvas", "unedited"
    )
    loaders: ClassVar[int] = 5

    def __init__(self, canvas: tk.Canvas):
        super(Animation, self).__init__()

        # ****** Animation Information ******
        self.delays: List[float] = []
        self.loaded = False
        self.frame_count = 1

        # ****** Canvas Information ******
        # PhotoImages are tkinter objects and thus
        # require a reference to a parent object.

        # since animations have to be reloaded
        # when the canvas is resized, these
        # values can be stored here.
        self.width = canvas.winfo_width()
        self.height = canvas.winfo_height()
        self.rotation = 0
        self.canvas = canvas

        # ****** Unedited Gif ******
        # used for faster loading
        self.unedited: Image.Image = None

    def __repr__(self):
        return "{}: w={} h={} r={}" + chr(176) + " loaded={}".format(
            self.__class__.__name__, self.width, self.height,
            self.rotation, self.loaded
        )

    def reload(self):
        self.clear()
        self.delays.clear()

        self.width = self.canvas.winfo_width()
        self.height = self.canvas.winfo_height()

        self.frame_count = 1
        self.loaded = False

    def start_load(self, filename: str, rotation: int, loop: asyncio.AbstractEventLoop = None):
        if loop is None:
            loop = asyncio.get_event_loop()
        loop.create_task(self.load(filename, rotation, loop))

    async def load(self, filename: str, rotation: int, loop: asyncio.AbstractEventLoop):
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
