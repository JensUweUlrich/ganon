import io
import os
import re

from setuptools import setup


def read(filename):
    filename = os.path.join(os.path.dirname(__file__), filename)
    text_type = type(u"")
    with io.open(filename, mode="r", encoding='utf-8') as fd:
        return re.sub(text_type(r':[a-z]+:`~?(.*?)`'), text_type(r'``\1``'), fd.read())

setup(
    name="ganon",
    version="1.1.2",
    url="https://www.github.com/pirovc/ganon",
    license='MIT',
    author="Vitor C. Piro",
    description="ganon is a k-mer based read classification tool which uses Interleaved Bloom Filters in conjunction with a taxonomic clustering and a k-mer counting-filtering scheme.",
    long_description=read("README.md"),
    package_dir={'': 'src'},
    packages=["ganon"],
    entry_points={'console_scripts': ['ganon=ganon.ganon:main_cli']},
    scripts=['scripts/ganon-get-seq-info.sh'],
    classifiers=[
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
    ],
)
