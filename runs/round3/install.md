# Round 3 local installation check

The first offline command incorrectly disabled build isolation. The environment has no directly installed `hatchling`, so wheel construction failed before installation (`install.log`). The project already correctly declares `hatchling` in `[build-system].requires`; changing product dependencies would not fix this invocation error. The corrected command keeps build isolation and uses only the existing local cache:

```sh
uv pip install --python .venv/bin/python --no-deps --offline --reinstall .
```

`install_verified.log` records successful build and installation. No network dependencies were requested, and no research run had started; there are no affected experimental arms to replay. The saved-refine preflight and cohort launcher independently compare every installed Python module byte against committed source before any model execution. The complete source was already covered by 894 passing offline tests, with one live test excluded (`integrated_suite.log`).
