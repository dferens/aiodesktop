import setuptools
from pathlib import Path

version = (0, 1, 1)
package_name = next(Path(__file__).parent.joinpath('src').iterdir()).name

with open('requirements.txt') as fp:
    requirements = fp.read().splitlines()

with open('README.md') as fp:
    long_description = fp.read()

setuptools.setup(
    name=package_name,
    version='.'.join(map(str, version)),
    author='Dmitriy Ferens',
    author_email='ferensdima@gmail.com',
    description='A set of tools which simplify building cross-platform desktop apps with Python, JavaScript, HTML & CSS.',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/dferens/{}'.format(package_name),
    packages=[package_name],
    package_dir={package_name: Path('src') / package_name},
    include_package_data=True,
    install_requires=requirements,
    keywords=['gui', 'html', 'javascript', 'electron', 'asyncio', 'websocket'],
    classifiers=[
        'Development Status :: 3 - Alpha',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
    ],
    python_requires='>=3.6',
)
