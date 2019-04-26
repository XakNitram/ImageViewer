"""
A class to handle loading gifs into tkinter asyncronously.
"""

from typing import List, ClassVar, TypeVar
import asyncio

from PIL.ImageTk import PhotoImage
from PIL import Image
import tkinter as tk
from math import ceil
from itertools import count


class Static:
    def __init__(self, canvas: tk.Canvas):
        super().__init__()

        self.image: PhotoImage = None

        # ****** Canvas Information ******
        self.canvas = canvas
        self.height = canvas.winfo_height()
        self.width = canvas.winfo_width()

        # ****** Unedited Image ******
        self.unedited: Image.Image = None

    def reload(self):
        self.width = self.canvas.winfo_width()
        self.height = self.canvas.winfo_height()

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

        # rotate the frame
        if rotation != 0:
            frame = await loop.run_in_executor(
                None, lambda: frame.rotate(-90 * rotation, expand=1)
            )

        # resize the frame to fit within the canvas
        frame = await loop.run_in_executor(
            None, lambda: frame.resize((w, h), Image.BILINEAR)
        )

        # convert the frame to the tkinter format
        self.image = PhotoImage(
            image=frame, master=self.canvas
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

    def reload(self):
        self.clear()
        self.delays.clear()

        self.width = self.canvas.winfo_width()
        self.height = self.canvas.winfo_height()

        self.frame_count = 1
        self.finished_loading = False

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
