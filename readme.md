# PackagesManager

The [Sublime Text](http://www.sublimetext.com) package manager. Visit
[packagecontrol.io](https://packagecontrol.io) for
[installation instructions](https://packagecontrol.io/installation), a list of
[available packages](https://packagecontrol.io/browse) and detailed
[documentation](https://packagecontrol.io/docs).


## Package Control

PackagesManager is my fork of the well know `Package Control`. But why, why, why a new name? Well I
was trying to develop it, but while trying to run it directly on my `Packages` folder (loose
packages), I got a bunch of errors due that `\ ` (space) between `Package` and `Control`. Therefore
you say ok then, but why the extra `s` on `Package`? Because while I was searching for a new name to
get rid of that `\ ` (space) I noticed that already there is a class named `PackageManager` inside
package control, so avoid any future headaches I decided the named should be changed. Then I added a
`s`, like in `Evandro's house` it would be `Package's Control`, i.e., now with `Package's Control`
your packages have the control, not you anymore.

Renaming it just removing the space as in `PackageControl` seemed not nice, as could much easily
confuse people much easily, as someone creating a new domain called `https://package-control.io`,
instead of the correct one, which would be `https://packagecontrol.io`.


## License

PackagesManager is licensed under the MIT license.

All of the source code (except for `packages_manager/semver.py`), is under the
license:

```
Copyright (c) 2011-2016 Will Bond <will@wbond.net>
Copyright (c) 2017 Evandro Coan <github.com/evandrocoan>

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
```

`packages_manager/semver.py` is under the license:

```
Copyright (c) 2013 Zachary King, FichteFoll

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
```
