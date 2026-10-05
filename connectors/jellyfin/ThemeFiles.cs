using System.Security.Cryptography;
using System.Text.Json.Serialization;

namespace Themerr.Connector;

public sealed record ThemeState(
    [property: JsonPropertyName("present")] bool Present,
    [property: JsonPropertyName("owned")] bool Owned,
    [property: JsonPropertyName("sha256")] string? Sha256);
public sealed class ThemeConflictException : Exception;

/// <summary>Writes only server-owned filenames beneath a library item's directory.</summary>
public sealed class ThemeFiles(ThemeOwnership ownership)
{
    private const long MaximumBytes = 104857600;
    private const string UserBackup = ".themerr-user-themes";
    private const string ThemeMusic = "theme-music";
    private const string UserMusicBackup = ".themerr-user-theme-music";
    private static readonly string[] ThemeNames =
        ["theme.m4a", "theme.opus", "theme.mp3", "theme.aac", "theme.ogg", "theme.oga",
         "theme.flac", "theme.wav", "theme.wma", "theme.aiff", "theme.aif", "theme.webm"];
    private static readonly Dictionary<string, string> Formats = new()
    {
        ["audio/mp4"] = "theme.m4a",
        ["audio/ogg"] = "theme.opus"
    };
    public ThemeState State(Guid itemId, string root, int themeSongCount = 0)
    {
        RejectDirectoryLink(root);
        var files = ThemeNames.Where(name => File.Exists(Path.Combine(root, name))).ToArray();
        var music = Path.Combine(root, ThemeMusic);
        RejectDirectoryLink(music);
        var present = files.Length > 0 || themeSongCount > 0 || Directory.Exists(music);
        var record = ownership.Find(itemId);
        // A database value selects a code-owned filename; it never becomes a path.
        var file = Formats.Values.FirstOrDefault(value => value == record?.File);
        if (file is null || files.Length != 1 || themeSongCount > 1 || Directory.Exists(music))
            return new(present, false, null);
        var path = Path.Combine(root, file);
        RejectLink(path);
        if (!File.Exists(path)) return new(present, false, null);
        using var stream = File.OpenRead(path);
        var digest = Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant();
        return new(true, digest == record!.Sha256, digest);
    }

    public async Task<ThemeState> Save(Guid itemId, string root, Stream body, string? contentType,
        string expectedDigest, int themeSongCount, CancellationToken cancellationToken,
        bool overwriteUser = false, bool backupUser = true)
    {
        if (contentType is null || !Formats.TryGetValue(contentType, out var file) ||
            expectedDigest.Length != 64 || !expectedDigest.All(Uri.IsHexDigit)) throw new InvalidDataException();
        var state = State(itemId, root, themeSongCount);
        if (state.Present && !state.Owned && !overwriteUser) throw new ThemeConflictException();
        var originals = Snapshot(root);
        var path = Path.Combine(root, file);
        RejectLink(path);
        var temporary = Path.Combine(root, Path.GetRandomFileName());
        try
        {
            var digest = await Write(body, temporary, cancellationToken).ConfigureAwait(false);
            if (!string.Equals(digest, expectedDigest, StringComparison.OrdinalIgnoreCase)) throw new InvalidDataException();
            ownership.Record(itemId, file, digest, () =>
            {
                // Recheck ownership and link boundaries after receiving the complete body.
                var current = State(itemId, root, themeSongCount);
                if ((current.Present && !current.Owned && !overwriteUser) ||
                    !originals.SequenceEqual(Snapshot(root))) throw new ThemeConflictException();
                RejectLink(path);
                if (current.Present && !current.Owned) ReplaceUserThemes(root, themeSongCount, backupUser);
                File.Move(temporary, path, true);
                foreach (var other in Formats.Values.Where(value => value != file))
                {
                    var old = Path.Combine(root, other);
                    RejectLink(old);
                    if (state.Owned && File.Exists(old)) File.Delete(old);
                }
            });
            return new(true, true, digest);
        }
        finally
        {
            File.Delete(temporary);
        }
    }

    private static async Task<string> Write(Stream body, string temporary, CancellationToken cancellationToken)
    {
        using var hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        await using var output = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None,
            65536, FileOptions.Asynchronous);
        var buffer = new byte[65536];
        long size = 0;
        int read;
        while ((read = await body.ReadAsync(buffer, cancellationToken).ConfigureAwait(false)) != 0)
        {
            size += read;
            if (size > MaximumBytes) throw new InvalidDataException();
            hash.AppendData(buffer, 0, read);
            await output.WriteAsync(buffer.AsMemory(0, read), cancellationToken).ConfigureAwait(false);
        }
        if (size == 0) throw new InvalidDataException();
        return Convert.ToHexString(hash.GetHashAndReset()).ToLowerInvariant();
    }

    private static void RejectLink(string path)
    {
        var info = new FileInfo(path);
        if (info.LinkTarget is not null || (info.Exists && (info.Attributes & FileAttributes.ReparsePoint) != 0))
            throw new ThemeConflictException();
    }

    private static void RejectDirectoryLink(string path)
    {
        var info = new DirectoryInfo(path);
        if (info.LinkTarget is not null || (info.Exists && (info.Attributes & FileAttributes.ReparsePoint) != 0))
            throw new ThemeConflictException();
    }

    private static string[] Snapshot(string root)
    {
        var snapshot = new List<string>();
        foreach (var name in ThemeNames)
        {
            var path = Path.Combine(root, name);
            RejectLink(path);
            if (!File.Exists(path)) continue;
            using var stream = File.OpenRead(path);
            snapshot.Add(name + ":" + Convert.ToHexString(SHA256.HashData(stream)));
        }
        var music = Path.Combine(root, ThemeMusic);
        RejectDirectoryLink(music);
        if (Directory.Exists(music)) snapshot.Add(Directory.GetLastWriteTimeUtc(music).Ticks.ToString());
        return snapshot.ToArray();
    }

    private static void ReplaceUserThemes(string root, int themeSongCount, bool backupUser)
    {
        var backup = Path.Combine(root, UserBackup);
        var music = Path.Combine(root, ThemeMusic);
        var musicBackup = Path.Combine(root, UserMusicBackup);
        RejectDirectoryLink(music);
        var names = ThemeNames.Where(name => File.Exists(Path.Combine(root, name))).ToArray();
        // Native themes outside these fixed resources must remain untouched.
        if (themeSongCount > names.Length && !Directory.Exists(music)) throw new ThemeConflictException();
        if (!backupUser)
        {
            // Validate every entry before recursive deletion, including directory junctions.
            if (Directory.Exists(music)) ValidateTree(new DirectoryInfo(music));
            foreach (var name in names) RejectLink(Path.Combine(root, name));
            foreach (var name in names) File.Delete(Path.Combine(root, name));
            if (Directory.Exists(music)) Directory.Delete(music, true);
            return;
        }
        RejectDirectoryLink(backup);
        RejectDirectoryLink(musicBackup);
        if (names.Any(name => File.Exists(Path.Combine(backup, name))) ||
            (Directory.Exists(music) && Directory.Exists(musicBackup))) throw new ThemeConflictException();
        Directory.CreateDirectory(backup);
        foreach (var name in names)
        {
            var source = Path.Combine(root, name);
            var destination = Path.Combine(backup, name);
            RejectLink(source);
            RejectLink(destination);
        }
        foreach (var name in names) File.Move(Path.Combine(root, name), Path.Combine(backup, name));
        if (Directory.Exists(music)) Directory.Move(music, musicBackup);
    }

    private static void ValidateTree(DirectoryInfo directory)
    {
        RejectDirectoryLink(directory.FullName);
        foreach (var entry in directory.GetFileSystemInfos())
        {
            if (entry.LinkTarget is not null || (entry.Attributes & FileAttributes.ReparsePoint) != 0)
                throw new ThemeConflictException();
            if (entry is DirectoryInfo child) ValidateTree(child);
        }
    }
}
