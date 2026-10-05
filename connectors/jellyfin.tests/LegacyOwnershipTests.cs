using System.Security.Cryptography;
using Microsoft.EntityFrameworkCore;
using Themerr.Connector;
using Xunit;

namespace Themerr.Connector.Tests;

/// <summary>Tests verified ownership imports without modifying the older plugin database.</summary>
public sealed class LegacyOwnershipTests : IDisposable
{
    private readonly string _root = Path.Combine(Path.GetTempPath(), $"themerr-import-test-{Guid.NewGuid()}");
    private readonly Guid _id = Guid.NewGuid();
    private readonly byte[] _audio = "original MP3 theme"u8.ToArray();

    /// <summary>Initializes a new instance of the <see cref="LegacyOwnershipTests"/> class.</summary>
    public LegacyOwnershipTests()
    {
        Directory.CreateDirectory(Media);
        File.WriteAllBytes(Path.Combine(Media, "theme.mp3"), _audio);
    }

    private string Media => Path.Combine(_root, "media");

    private string Data => Path.Combine(_root, "data");

    private string Database => Path.Combine(Data, "Themerr", "themerr.db");

    private string Digest => Convert.ToHexString(SHA256.HashData(_audio)).ToLowerInvariant();

    private ThemeFiles Files => new(new ThemeOwnership(Data));

    /// <inheritdoc/>
    public void Dispose() => Directory.Delete(_root, true);

    /// <summary>Checks that verified MP3 ownership can be imported and upgraded while the old database stays unchanged.</summary>
    /// <returns>The asynchronous test execution.</returns>
    [Fact]
    public async Task VerifiedMp3OwnershipCanBeImportedAndUpgradedWithoutTouchingTheOldDatabase()
    {
        Seed(new LegacyRow
        {
            ItemId = _id.ToString("N"),
            ThemeHash = Digest.ToUpperInvariant(),
        });
        var original = SHA256.HashData(await File.ReadAllBytesAsync(Database, TestContext.Current.CancellationToken));
        Assert.False(Files.State(_id, Media).Owned);
        var digest = new LegacyOwnership(Data).Hash(_id);
        Assert.True(Files.Import(_id, Media, digest, 1).Owned);
        Assert.Equal(original, SHA256.HashData(await File.ReadAllBytesAsync(Database, TestContext.Current.CancellationToken)));
        Assert.True(File.Exists(Path.Combine(Media, "theme.mp3")));
        await Files.Save(_id, Media, new MemoryStream(_audio), "audio/mp4", Digest, 1, CancellationToken.None);
        Assert.False(File.Exists(Path.Combine(Media, "theme.mp3")));
        Assert.True(Files.State(_id, Media).Owned);
        Assert.False(Directory.Exists(Path.Combine(Media, ".themerr-user-themes")));
    }

    /// <summary>Checks that user themes, unsupported digests, and changed audio cannot authorize an import.</summary>
    /// <param name="provider">The theme provider recorded by the older plugin.</param>
    /// <param name="algorithm">The digest algorithm recorded by the older plugin.</param>
    /// <param name="changed">Whether the user replaced the recorded theme audio.</param>
    [Theory]
    [InlineData("user", "SHA256", false)]
    [InlineData("themerr", "MD5", false)]
    [InlineData("themerr", "SHA256", true)]
    public void UserThemesOldHashesAndManuallyChangedFilesRemainProtected(string provider, string algorithm, bool changed)
    {
        Seed(new LegacyRow
        {
            ItemId = _id.ToString("D"),
            ThemeHash = Digest,
            ThemeProvider = provider,
            ThemeHashAlgorithm = algorithm,
        });
        if (changed)
        {
            File.WriteAllText(Path.Combine(Media, "theme.mp3"), "user replacement");
        }

        Assert.False(Files.Import(_id, Media, new LegacyOwnership(Data).Hash(_id), 1).Owned);
        Assert.Null(new ThemeOwnership(Data).Find(_id));
        Assert.True(File.Exists(Path.Combine(Media, "theme.mp3")));
    }

    /// <summary>Checks that missing or ambiguous legacy rows cannot authorize ownership.</summary>
    [Fact]
    public void MissingUnmatchedOrAmbiguousRowsCannotAuthorizeOwnership()
    {
        Assert.Null(new LegacyOwnership(Data).Hash(_id));
        Seed(
            new LegacyRow
            {
                ItemId = _id.ToString("N"),
                ThemeHash = Digest,
            },
            new LegacyRow
            {
                ItemId = _id.ToString("D"),
                ThemeHash = Digest,
                ThemeProvider = "user",
            });
        Assert.Null(new LegacyOwnership(Data).Hash(_id));
        Assert.Null(new LegacyOwnership(Data).Hash(Guid.NewGuid()));
    }

    /// <summary>Checks that ownership requires a valid digest matching the current audio.</summary>
    /// <param name="digest">The candidate SHA-256 digest.</param>
    [Theory]
    [InlineData(null)]
    [InlineData("md5")]
    [InlineData("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")]
    [InlineData("zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz")]
    public void MissingInvalidOrDifferentHashesCannotAuthorizeOwnership(string? digest) =>
        Assert.False(Files.Import(_id, Media, digest).Owned);

    /// <summary>Checks that multiple themes keep legacy ownership ambiguous and protected.</summary>
    /// <param name="extraFile">Whether an additional theme file makes ownership ambiguous.</param>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void MultipleThemeFilesOrNativeSongsRemainProtected(bool extraFile)
    {
        if (extraFile)
        {
            File.WriteAllBytes(Path.Combine(Media, "theme.m4a"), _audio);
        }

        Assert.False(Files.Import(_id, Media, Digest, extraFile ? 1 : 2).Owned);
    }

    private void Seed(params LegacyRow[] rows)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(Database)!);
        using var context = new LegacySeedContext(new DbContextOptionsBuilder<LegacySeedContext>()
            .UseSqlite(new Microsoft.Data.Sqlite.SqliteConnectionStringBuilder
            {
                DataSource = Database,
                Pooling = false,
            }.ToString()).Options);
        context.Database.EnsureCreated();
        context.Themes.AddRange(rows);
        context.SaveChanges();
    }
}
