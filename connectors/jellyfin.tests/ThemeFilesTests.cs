using System.Security.Cryptography;
using System.Diagnostics;
using Themerr.Connector;
using Xunit;

namespace Themerr.Connector.Tests;

public sealed class ThemeFilesTests : IDisposable
{
    private readonly string _root = Path.Combine(Path.GetTempPath(), "themerr-connector-test-" + Guid.NewGuid());
    private readonly byte[] _audio = "complete validated audio"u8.ToArray();
    private string Digest => Convert.ToHexString(SHA256.HashData(_audio)).ToLowerInvariant();
    public ThemeFilesTests() => Directory.CreateDirectory(_root);
    public void Dispose() => Directory.Delete(_root, true);
    private string FilePath(string name) => Path.Combine(_root, name);
    private Task<ThemeState> Save(string? type = "audio/mp4", string? digest = null, int count = 0,
        bool overwrite = false, Stream? stream = null, bool backup = true) => ThemeFiles.Save(_root,
            stream ?? new MemoryStream(_audio), type, digest ?? Digest, count, CancellationToken.None, overwrite, backup);

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task WindowsJunctionsNeverDeleteSiblingThemes(bool nested)
    {
        if (!OperatingSystem.IsWindows()) Assert.Skip("Windows junction test.");
        var sibling = _root + "-sibling";
        Directory.CreateDirectory(sibling);
        var outside = Path.Combine(sibling, "outside.mp3");
        File.WriteAllText(outside, "outside theme");
        var music = FilePath("theme-music");
        if (nested) Directory.CreateDirectory(music);
        var link = nested ? Path.Combine(music, "nested") : music;
        var command = new ProcessStartInfo(Path.Combine(Environment.SystemDirectory, "cmd.exe"))
        { UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true, RedirectStandardError = true };
        foreach (var argument in new[] { "/c", "mklink", "/J", link, sibling }) command.ArgumentList.Add(argument);
        try
        {
            using var process = Process.Start(command)!;
            await process.WaitForExitAsync(TestContext.Current.CancellationToken);
            Assert.Equal(0, process.ExitCode);
            await Assert.ThrowsAsync<ThemeConflictException>(() => Save(count: 1, overwrite: true, backup: false));
            Assert.Equal("outside theme", File.ReadAllText(outside));
        }
        finally
        {
            if (Directory.Exists(link)) Directory.Delete(link);
            Directory.Delete(sibling, true);
        }
    }

    [Fact]
    public async Task ReplacementCanRemoveUserThemesWithoutCreatingBackups()
    {
        File.WriteAllText(FilePath("theme.mp3"), "user theme");
        var music = Directory.CreateDirectory(FilePath("theme-music"));
        File.WriteAllText(Path.Combine(music.FullName, "user.mp3"), "another theme");
        await Save(count: 2, overwrite: true, backup: false);
        Assert.True(ThemeFiles.State(_root).Owned);
        Assert.False(File.Exists(FilePath("theme.mp3")));
        Assert.False(Directory.Exists(music.FullName));
        Assert.False(Directory.Exists(FilePath(".themerr-user-themes")));
        Assert.False(Directory.Exists(FilePath(".themerr-user-theme-music")));
    }

    [Theory]
    [InlineData(null)]
    [InlineData("../../file")]
    [InlineData("audio/mp3")]
    public async Task RejectsUnknownContentTypes(string? type)
    {
        await Assert.ThrowsAsync<InvalidDataException>(() => Save(type));
        Assert.Empty(Directory.GetFiles(_root));
    }

    [Theory]
    [InlineData("short")]
    [InlineData("zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz")]
    [InlineData("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")]
    public async Task RejectsInvalidOrMismatchedHashes(string digest)
    {
        await Assert.ThrowsAsync<InvalidDataException>(() => Save(digest: digest));
        Assert.Empty(Directory.GetFiles(_root));
    }

    [Fact]
    public async Task RejectsEmptyAudioAndCleansTemporaryFiles()
    {
        await Assert.ThrowsAsync<InvalidDataException>(() => Save(stream: new MemoryStream()));
        Assert.Empty(Directory.GetFiles(_root));
    }

    [Fact]
    public async Task SavesVerifiedAudioAndSwitchesFormats()
    {
        Assert.False(ThemeFiles.State(_root).Present);
        var saved = await Save();
        Assert.True(saved.Owned);
        Assert.Equal(Digest, saved.Sha256);
        Assert.True(ThemeFiles.State(_root).Owned);
        Assert.False(ThemeFiles.State(_root, 2).Owned);
        await Assert.ThrowsAsync<ThemeConflictException>(() => Save(count: 2));
        await Save("audio/ogg", Digest.ToUpperInvariant());
        Assert.False(File.Exists(FilePath("theme.m4a")));
        Assert.Equal(_audio, File.ReadAllBytes(FilePath("theme.opus")));
    }

    [Fact]
    public async Task PreservesUserThemesByDefaultIncludingManuallyEditedUploads()
    {
        File.WriteAllText(FilePath("theme.mp3"), "user theme");
        await Assert.ThrowsAsync<ThemeConflictException>(() => Save());
        Assert.Equal("user theme", File.ReadAllText(FilePath("theme.mp3")));
        File.Delete(FilePath("theme.mp3"));
        await Save();
        File.WriteAllText(FilePath("theme.m4a"), "manually changed");
        Assert.False(ThemeFiles.State(_root).Owned);
        await Assert.ThrowsAsync<ThemeConflictException>(() => Save());
        Assert.Equal("manually changed", File.ReadAllText(FilePath("theme.m4a")));
    }

    [Theory]
    [InlineData("theme.mp3")]
    [InlineData("theme.m4a")]
    [InlineData("theme.opus")]
    public async Task ExplicitReplacementBacksUpUserFiles(string name)
    {
        File.WriteAllText(FilePath(name), "user theme");
        var state = await Save(overwrite: true);
        Assert.True(state.Owned);
        Assert.True(ThemeFiles.State(_root).Owned);
        Assert.Equal("user theme", File.ReadAllText(Path.Combine(_root, ".themerr-user-themes", name)));
        Assert.Equal(_audio, File.ReadAllBytes(FilePath("theme.m4a")));
    }

    [Fact]
    public async Task ReplacementBacksUpThemeMusicFolderAndNeverOverwritesEarlierBackups()
    {
        var music = FilePath("theme-music");
        Directory.CreateDirectory(music);
        File.WriteAllText(Path.Combine(music, "my song.mp3"), "user theme");
        Assert.True(ThemeFiles.State(_root).Present);
        await Assert.ThrowsAsync<ThemeConflictException>(() => Save(count: 1));
        await Save(count: 1, overwrite: true);
        Assert.Equal("user theme", File.ReadAllText(Path.Combine(_root, ".themerr-user-theme-music", "my song.mp3")));
        Directory.CreateDirectory(music);
        File.WriteAllText(Path.Combine(music, "second.mp3"), "another theme");
        await Assert.ThrowsAsync<ThemeConflictException>(() => Save(count: 2, overwrite: true));
        Assert.True(File.Exists(Path.Combine(music, "second.mp3")));
    }

    [Fact]
    public async Task NativeThemesOutsideFixedResourcesStayProtected()
    {
        await Assert.ThrowsAsync<ThemeConflictException>(() => Save(count: 1, overwrite: true));
        Assert.False(File.Exists(FilePath("theme.m4a")));
    }

    [Theory]
    [InlineData("not json")]
    [InlineData("null")]
    [InlineData("{\"File\":\"../outside.m4a\",\"Sha256\":\"anything\"}")]
    public async Task CorruptOrTraversingOwnershipDoesNotAuthorizeReplacement(string ownership)
    {
        File.WriteAllText(FilePath("theme.m4a"), "user theme");
        File.WriteAllText(FilePath(".themerr-connector.json"), ownership);
        Assert.False(ThemeFiles.State(_root).Owned);
        await Assert.ThrowsAsync<ThemeConflictException>(() => Save());
    }

    [Fact]
    public async Task OwnershipWithoutItsFileIsNotOwned()
    {
        await Save();
        File.Delete(FilePath("theme.m4a"));
        Assert.False(ThemeFiles.State(_root).Present);
        Assert.False(ThemeFiles.State(_root).Owned);
    }

    [Theory]
    [InlineData("theme.m4a", false)]
    [InlineData(".themerr-connector.json", false)]
    [InlineData("theme-music", true)]
    [InlineData(".themerr-user-themes", true)]
    public async Task RejectsLinksIntoSiblingDirectories(string name, bool directory)
    {
        var sibling = _root + "-sibling";
        Directory.CreateDirectory(sibling);
        var target = Path.Combine(sibling, "outside.m4a");
        File.WriteAllText(target, "outside");
        try
        {
            try
            {
                if (directory) Directory.CreateSymbolicLink(FilePath(name), sibling);
                else File.CreateSymbolicLink(FilePath(name), target);
            }
            catch (UnauthorizedAccessException) { Assert.Skip("Symbolic link creation privilege unavailable."); }
            catch (IOException error) when (OperatingSystem.IsWindows() && (error.HResult & 0xffff) == 1314)
            { Assert.Skip("Symbolic link creation privilege unavailable."); }
            File.WriteAllText(FilePath("theme.mp3"), "user theme");
            await Assert.ThrowsAsync<ThemeConflictException>(() => Save(overwrite: true));
            Assert.Equal("outside", File.ReadAllText(target));
        }
        finally { Directory.Delete(sibling, true); }
    }
}
