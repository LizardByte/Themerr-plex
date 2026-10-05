using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Themerr.Connector;

public sealed record ThemeState(
    [property: JsonPropertyName("present")] bool Present,
    [property: JsonPropertyName("owned")] bool Owned,
    [property: JsonPropertyName("sha256")] string? Sha256);
public sealed class ThemeConflictException : Exception;

/// <summary>Writes only server-owned filenames beneath a library item's directory.</summary>
public static class ThemeFiles
{
    private const string OwnershipFile = ".themerr-connector.json";
    private const long MaximumBytes = 104857600;
    private static readonly Dictionary<string, string> Formats = new()
    {
        ["audio/mp4"] = "theme.m4a",
        ["audio/ogg"] = "theme.opus"
    };
    private sealed record Ownership(string File, string Sha256);

    public static ThemeState State(string root, int themeSongCount = 0)
    {
        var files = Directory.GetFiles(root, "theme.*");
        var present = files.Length > 0 || themeSongCount > 0;
        var metadata = Path.Combine(root, OwnershipFile);
        RejectLink(metadata);
        if (!File.Exists(metadata)) return new(present, false, null);
        Ownership? ownership;
        try { ownership = JsonSerializer.Deserialize<Ownership>(File.ReadAllText(metadata)); }
        catch (JsonException) { return new(present, false, null); }
        // A metadata value selects a code-owned filename; it never becomes a path.
        var file = Formats.Values.FirstOrDefault(value => value == ownership?.File);
        if (file is null || files.Length != 1 || themeSongCount > 1) return new(present, false, null);
        var path = Path.Combine(root, file);
        RejectLink(path);
        if (!File.Exists(path)) return new(present, false, null);
        using var stream = File.OpenRead(path);
        var digest = Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant();
        return new(true, digest == ownership!.Sha256, digest);
    }

    public static async Task<ThemeState> Save(string root, Stream body, string? contentType,
        string expectedDigest, int themeSongCount, CancellationToken cancellationToken)
    {
        if (contentType is null || !Formats.TryGetValue(contentType, out var file) ||
            expectedDigest.Length != 64 || !expectedDigest.All(Uri.IsHexDigit)) throw new InvalidDataException();
        var state = State(root, themeSongCount);
        if (state.Present && !state.Owned) throw new ThemeConflictException();
        var path = Path.Combine(root, file);
        var metadata = Path.Combine(root, OwnershipFile);
        RejectLink(path);
        RejectLink(metadata);
        var temporary = Path.Combine(root, Path.GetRandomFileName());
        var metadataTemporary = Path.Combine(root, Path.GetRandomFileName());
        try
        {
            var digest = await Write(body, temporary, cancellationToken).ConfigureAwait(false);
            if (!string.Equals(digest, expectedDigest, StringComparison.OrdinalIgnoreCase)) throw new InvalidDataException();
            await using (var metadataStream = new FileStream(metadataTemporary, FileMode.CreateNew,
                FileAccess.Write, FileShare.None, 4096, FileOptions.Asynchronous))
            {
                await JsonSerializer.SerializeAsync(metadataStream, new Ownership(file, digest),
                    cancellationToken: cancellationToken).ConfigureAwait(false);
            }
            // Recheck the ownership and link boundaries after receiving the complete body.
            var current = State(root, themeSongCount);
            if (current.Present && (!current.Owned || current.Sha256 != state.Sha256)) throw new ThemeConflictException();
            RejectLink(path);
            RejectLink(metadata);
            File.Move(temporary, path, true);
            File.Move(metadataTemporary, metadata, true);
            foreach (var other in Formats.Values.Where(value => value != file))
            {
                var old = Path.Combine(root, other);
                RejectLink(old);
                if (state.Owned && File.Exists(old)) File.Delete(old);
            }
            return new(true, true, digest);
        }
        finally
        {
            File.Delete(temporary);
            File.Delete(metadataTemporary);
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
}
