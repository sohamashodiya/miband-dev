# vendor/

Third-party code the faces build with. This folder ships in the miband-dev plugin
(`${CLAUDE_PLUGIN_ROOT}/vendor/`: this README and `patches/`). The toolkit itself is a git clone in
**your workspace**, `vendor/band10-toolkit/` (gitignored there); keep your own copy of the patch in
`vendor/patches/` if you change the toolkit.

## band10-toolkit

- Upstream: https://github.com/utsabfdahal/band10-toolkit (branch `main`)
- Pinned commit: `549abf5046ce207327ca82fdc20b0320c27a3830` (2026-08-17, "docs(readme): mark faces as verified on a physical Band 10 via the Notify app")
- Our changes: `patches/band10-toolkit.patch` (the clone's working tree = that commit + this patch)

What the patch does:
| File | Change |
|---|---|
| `builder/gmf.ts` | A face's optional `script/` folder (entry `main.lua`) is copied next to `wfDef.json` and packed as a type-5 Lua element, drawn on top of the face. Faces use it to draw a centred time and date. |
| `builder/native.ts` | The native o66 packer writes the script element as type-5 Lua resources (`lua/<file>`, byte-identical to m0tral's EasyFace output) and folds long data-source IDs. |
| `core/dataSources.ts`, `parser/binary.ts` | `normalizeDataSource()`: long FPRJ source IDs fold as modifier + base (`40009031` °F → `D031`). Verified on a Band 11 (fw 4.100.139), 2026-09-24. |
| `docs/research.md` | Records the °F finding. |
| `package.json`, `package-lock.json` | Adds `fontkit` (the face generators render glyphs with it). |
| `cli/index.ts` | Resolves project paths from the folder `npm` was started in (`INIT_CWD`), so `npm --prefix vendor/band10-toolkit run band10 -- package faces/<name>` works from the workspace root. |

Your faces live in the workspace's `faces/<name>/`, not in the toolkit's `examples/`. The toolkit's
own examples stay as upstream.

### Set up from scratch

From the workspace root (once per workspace):

```sh
mkdir -p vendor/patches
cp "${CLAUDE_PLUGIN_ROOT}/vendor/patches/band10-toolkit.patch" vendor/patches/
git clone https://github.com/utsabfdahal/band10-toolkit.git vendor/band10-toolkit
git -C vendor/band10-toolkit checkout 549abf5046ce207327ca82fdc20b0320c27a3830
git -C vendor/band10-toolkit apply ../patches/band10-toolkit.patch
(cd vendor/band10-toolkit && npm install)
mkdir -p faces && cp "${CLAUDE_PLUGIN_ROOT}/skills/new-project/templates/faces-package.json" faces/package.json
(cd faces && npm run setup)          # faces/node_modules -> ../vendor/band10-toolkit/node_modules
```

### Changing the toolkit

Edit files in `vendor/band10-toolkit/`, then refresh the patch and commit it in your workspace:

```sh
git -C vendor/band10-toolkit diff > vendor/patches/band10-toolkit.patch
```

Before resetting or updating the clone, **always save the diff first** (the command above). To move
to a newer upstream: save the diff, `git -C vendor/band10-toolkit checkout -- . && git -C vendor/band10-toolkit pull`,
`git apply --3way ../patches/band10-toolkit.patch`, fix conflicts, rebuild every face and check the `.bin`
matches (or explain why not), then refresh the patch and update the pinned commit above.

### Check

```sh
(cd vendor/band10-toolkit && npx vitest run)                       # 32 tests, 2026-09-28
npm --prefix vendor/band10-toolkit run band10 -- package faces/<name>   # each of your faces
```
