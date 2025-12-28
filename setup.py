from setuptools import setup, find_packages
import src

with open('README.md', 'r', encoding='utf-8') as f:
    long_description = f.read()

with open('requirements.txt', 'r', encoding='utf-8') as f:
    requirements = f.read()

setup(
    name=src.__title__,
    version=src.__version__,
    install_requires=requirements.split('\n'),
    long_description=long_description,
    long_description_content_type='text/markdown',
    packages=find_packages(),
    include_package_data=True,
    zip_safe=True,
    url=src.__license__,
    license=src.__license__,
    author=src.__author__,
    author_email=src.__email__,
    description=src.__description__,
    entry_points={'console_scripts': ['musicdl = src.main']},
)
