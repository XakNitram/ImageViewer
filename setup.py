from setuptools import setup


setup(
    name="tkexpanded",
    packages=["tkexpanded"],
    version="0.0.0",
    description=("Extension of tkinter with a "
                 "collection of objects aimed "
                 "at simplifying complex programs "
                 "made with tkinter"
                 ),
    author="Tate Mioton",
    author_email="tatemioton@outlook.com",
    url="https://github.com/XakNitram/tkexpanded",
    install_requires=[
        "tkinter>=8.6"
    ]
)
