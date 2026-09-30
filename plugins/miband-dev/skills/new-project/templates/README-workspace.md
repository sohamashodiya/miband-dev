# <Workspace name>

Band apps and watch faces for Xiaomi Smart Bands, built with the miband-dev Claude Code plugin.

## Projects

| Project | Folder | Kind | Devices | Status | On the device | Design |
|---|---|---|---|---|---|---|
| <Project> | `apps/<name>/` | band app + phone companion | <phone>, <band> | <status> | band <x.y.z>, phone <x.y.z> | <link or path> |
| <Face> | `faces/<name>/` | watch face | <band> | <status> | ID `<id>` (v<x.y.z>) | <link or path> |

## Layout

```
README.md            this map + project registry (one row per project)
devices/             DEVICES.md; <model>/profile.json (your calibration), evidence/, photos/ (ignored)
apps/<project>/      a band app + phone companion: PROJECT.md, band/, phone/, (design/)
faces/<project>/     a watch face: PROJECT.md, generate.ts, layout.json, manifest.json, assets/, script/
faces/package.json   runs the toolkit CLI for any face
vendor/              band10-toolkit clone (ignored) + patches/band10-toolkit.patch
tools/               workspace copies of the calibration kits (only when you build them)
signing/             the shared key (keys ignored; back them up privately)
```
