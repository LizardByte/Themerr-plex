# Repository guidance

## Filesystem paths and web endpoints

- Trace request data through to filesystem operations before adding or changing an endpoint.
  Prefer resource identifiers mapped to fixed, server-owned filenames. Never interpolate a
  request value into a filename, directory, or path, even after checking membership or a regex.
  The log viewer's fixed `_LOG_FILES` mapping is an example.
- Use `common.path_policy.resolve_file_path(trusted_directory, relative_filename)` for existing
  files beneath a permitted root. It validates components before normalization, resolves symlinks
  and Windows junctions, and checks canonical containment. The directory must come from application
  code or trusted configuration, never from a request. Use `validate_relative_path` when validating
  a relative name without reading a file.
- HTTP file endpoints must use `common.http.file_response`; compiled assets must use
  `common.http.SafeStaticFiles` with `follow_symlink=False`. These share the path policy.
  Do not return `FileResponse` or call `open` on a request-derived path directly. Keep checks at
  the filesystem boundary so background readers and future endpoints reuse the same protection;
  an endpoint decorator alone does not protect those other callers.
- Reject traversal, absolute/drive/UNC paths, backslashes, encoded separators, dot segments,
  Windows reserved names, control characters, alternate data streams, and links escaping the root.
  Never use a bare string-prefix comparison to establish containment or fall back to an unchecked
  path after validation fails. Return fixed client errors and log unexpected details server-side.
- An intentional directory picker may accept an administrator-selected absolute directory to
  list metadata. Preserve authentication and CSRF protection, validate its purpose, and never
  reuse that exception to serve file contents or to broaden an unrelated endpoint's root.
- Test both accepted resources and rejected paths, including encoded traversal, Windows forms,
  and symlink/junction escapes to similarly named sibling directories. Keep external services mocked.

## Validation

- Run targeted pytest tests with `-o addopts='' -p no:cacheprovider` and `--basetemp` outside the
  checkout. Keep coverage and JUnit output outside the checkout as well.
- Run flake8 and `git diff --check` for Python changes, `npm test` and `npm run build` for browser
  changes, and `python -m dockle build` for documentation or public docstring changes.
- Query the current PR's Sonar and CodeQL findings before remediation. Preserve the PR filter
  and distinguish local validation from hosted reanalysis. Do not suppress or dismiss findings
  just to pass a gate. Commit and push only when the user requests those actions.
