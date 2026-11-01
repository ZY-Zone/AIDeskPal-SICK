# Bundled plugins

Folders placed here are picked up by the plugin manager at start-up, next to the
plugins installed from the market (`user_data/plugins`). Each folder needs a
`plugin.json` manifest and the entry module it names.

No plugin ships with the repository: the previous `com.aideskpal.focus_orbit`
example was removed. See `docs/plugin-development.md` for the manifest format,
the permission list and the `setup(api)` entry point. Drop a plugin folder in
here to load it; there is nothing to enable by default.
