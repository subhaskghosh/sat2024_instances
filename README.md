# SAT2024 ASCII transfer

Copy this entire directory, including all files in parts/, to the destination
machine. Every file in this transfer directory is ASCII text.

Contents: 400 benchmark instances (.cnf.xz) and one .uri file from SAT2024.
The original file bytes, names, and relative paths are preserved. The .xz
instances remain compressed; reconstruction does not expand the CNF data.

The folder was archived as SAT2024.tar.gz, Base64 encoded with 76-character
lines, then split into ordered parts of at most 50 MiB (52,428,800 bytes).
Part boundaries can occur within a Base64 line; concatenate before decoding.

## Reconstruct on macOS or Linux

Requirements: Python 3 (standard library only), and an existing destination
parent directory with approximately 8.8 GB of free space, in addition to this
transfer directory. No network access or package installation is needed.

From this transfer directory:

```sh
sh reconstruct.sh /path/to/existing/destination-parent
```

This creates /path/to/existing/destination-parent/SAT2024 and refuses to
overwrite any existing SAT2024 path. It verifies the transfer metadata, every
part, the decoded archive, and all 401 restored file hashes before publishing
the folder. Temporary files are removed on success or failure. A partial
destination is retained for inspection if the final publishing step fails.
Archive links, special files, unexpected members, duplicate files, and unsafe
paths are rejected. Do not run two reconstructions into the same parent.

An omitted destination argument uses the current working directory.

## Optional independent checksum checks

On macOS, from this transfer directory:

```sh
shasum -a 256 -c metadata.sha256
shasum -a 256 -c parts.sha256
```

On Linux, use sha256sum -c in place of shasum -a 256 -c.
After reconstruction, from the destination parent:

```sh
shasum -a 256 -c /path/to/SAT2024-ascii-transfer/files.sha256
```

manifest.json records exact byte counts, part count, original file metadata,
and per-file SHA-256 values. archive.sha256 describes the intermediate archive;
the binary archive is not shipped separately. The source folder is unmodified.
