# FLiberator

FLiberator is a small open-source software package that does exactly one thing: it liberate downloadable Florida statutes from a weird proprietary format.

License: MIT

## Install

FLiberator is managed with [`uv`](https://docs.astral.sh/uv/) and requires Python 3.12+.

```bash
uv sync
```

This installs the `fliberator` package (in editable mode) into a local `.venv`, importable as:

```python
import fliberator
```

## Steps

1. FLiberator downloads, into a git-ignored working folder, the "Advanced Legislative Search & Browse" application zip file from its [download page](https://www.leg.state.fl.us/Statutes/index.cfm?Mode=Statutes%20Download&Submenu=7&Tab=statutes). The current link for the 2025 statutes is <https://www.leg.state.fl.us/Statutes/FLLawDL2025.zip>.
3. FLiberator unzips the file.
4. FLiberator converts the Rocket NXT (`.NXT`) files to Folio Flat File (`.FFF`) format. (How to do this is TBD!)
5. FLiberator converts the `.FFF` files to XML.  (The Apache 2.0-licensed [`folioxml`](https://github.com/imazen/folioxml) package should do this.)

## Background

- Florida provides an downloadable Windows desktop application called "Advanced Legislative Search & Browse", which contains a bulk dataset of the Florida statutes: <https://www.leg.state.fl.us/Statutes/index.cfm?Mode=Statutes%20Download&Submenu=7&Tab=statutes>.
- After extracting the zip file for the application, there are several `.nxt` files. This is a proprietary (?) format produced by [Rocket® NXT software](https://www.rocketsoftware.com/en-us/products/folio-nxt/nxt).
- The Florida statutes file is `Library/fs2025.nxt`.
- This must first be converted from NXT format to the more open "Folio Flat File" (`.fff`) format.
- Once `.fff` files are obtained, these can be converted to XML with the open-source [folioxml](https://github.com/imazen/folioxml) software.
