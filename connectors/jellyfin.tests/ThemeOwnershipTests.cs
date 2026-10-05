using System.Diagnostics;
using Microsoft.Data.Sqlite;
using Themerr.Connector;
using Xunit;

namespace Themerr.Connector.Tests;

public sealed class ThemeOwnershipTests : IDisposable
{
    private readonly string _root = Path.Combine(Path.GetTempPath(), "themerr-ownership-test-" + Guid.NewGuid());
    private string DirectoryPath => Path.Combine(_root, "themerr-connector");
    private string DatabasePath => Path.Combine(DirectoryPath, "ownership.db");
    private readonly ThemeOwnership _ownership;

    public ThemeOwnershipTests()
    {
        Directory.CreateDirectory(_root);
        _ownership = new ThemeOwnership(_root);
    }

    public void Dispose() => Directory.Delete(_root, true);

    [Fact]
    public void ReadingMissingOwnershipDoesNotCreateFiles()
    {
        Assert.Null(_ownership.Find(Guid.NewGuid()));
        Assert.Empty(Directory.GetFileSystemEntries(_root));
    }

    [Fact]
    public void MultipleItemsAndFormatChangesPersistInOneDatabaseAcrossInstances()
    {
        var first = Guid.NewGuid();
        var second = Guid.NewGuid();
        _ownership.Record(first, "theme.m4a", "first", () => { });
        _ownership.Record(second, "theme.m4a", "second", () => { });
        _ownership.Record(first, "theme.opus", "replacement", () => { });
        var reopened = new ThemeOwnership(_root);
        Assert.Equal(new Ownership("theme.opus", "replacement"), reopened.Find(first));
        Assert.Equal(new Ownership("theme.m4a", "second"), reopened.Find(second));
        Assert.Null(reopened.Find(Guid.NewGuid()));
        Assert.Equal([DatabasePath], Directory.GetFiles(DirectoryPath));
        using var database = new SqliteConnection(new SqliteConnectionStringBuilder
            { DataSource = DatabasePath, Pooling = false }.ToString());
        database.Open();
        using var count = database.CreateCommand();
        count.CommandText = "SELECT COUNT(*) FROM theme_ownership";
        Assert.Equal(2L, count.ExecuteScalar());
    }

    [Fact]
    public void FailedAudioWritesNeverCommitOwnership()
    {
        var id = Guid.NewGuid();
        Assert.Throws<IOException>(() => _ownership.Record(id, "theme.m4a", "failed", () => throw new IOException()));
        Assert.Null(_ownership.Find(id));
        _ownership.Record(id, "theme.m4a", "original", () => { });
        Assert.Throws<IOException>(() => _ownership.Record(id, "theme.opus", "failed", () => throw new IOException()));
        Assert.Equal(new Ownership("theme.m4a", "original"), new ThemeOwnership(_root).Find(id));
    }

    [Fact]
    public async Task ConcurrentItemsKeepSeparateRecords()
    {
        var ids = Enumerable.Range(0, 8).Select(_ => Guid.NewGuid()).ToArray();
        await Task.WhenAll(ids.Select(id => Task.Run(() =>
            new ThemeOwnership(_root).Record(id, "theme.m4a", id.ToString("N"), () => { }))));
        foreach (var id in ids) Assert.Equal(id.ToString("N"), _ownership.Find(id)!.Sha256);
        Assert.Equal([DatabasePath], Directory.GetFiles(DirectoryPath));
    }

    [Fact]
    public void BrokenDatabasesNeverAuthorizeOrWriteAudio()
    {
        Directory.CreateDirectory(DirectoryPath);
        File.WriteAllText(DatabasePath, "invalid database");
        Assert.Throws<SqliteException>(() => _ownership.Find(Guid.NewGuid()));
        var wroteAudio = false;
        Assert.Throws<SqliteException>(() => _ownership.Record(Guid.NewGuid(), "theme.m4a", "digest",
            () => wroteAudio = true));
        Assert.False(wroteAudio);
        Assert.Equal("invalid database", File.ReadAllText(DatabasePath));
    }

    [Theory]
    [InlineData("ownership.db")]
    [InlineData("ownership.db-journal")]
    [InlineData("ownership.db-wal")]
    [InlineData("ownership.db-shm")]
    public void DatabaseAndJournalLinksCannotAccessSiblingFiles(string filename)
    {
        Directory.CreateDirectory(DirectoryPath);
        var outside = Path.Combine(_root, "outside.db");
        File.WriteAllText(outside, "outside");
        try { File.CreateSymbolicLink(Path.Combine(DirectoryPath, filename), outside); }
        catch (UnauthorizedAccessException) { Assert.Skip("Symbolic link creation privilege unavailable."); }
        catch (IOException error) when (OperatingSystem.IsWindows() && (error.HResult & 0xffff) == 1314)
        { Assert.Skip("Symbolic link creation privilege unavailable."); }
        Assert.Throws<ThemeConflictException>(() => _ownership.Find(Guid.NewGuid()));
        Assert.Throws<ThemeConflictException>(() => _ownership.Record(Guid.NewGuid(), "theme.m4a", "digest", () => { }));
        Assert.Equal("outside", File.ReadAllText(outside));
    }

    [Fact]
    public async Task DatabaseDirectoryJunctionCannotAccessSiblingFiles()
    {
        if (!OperatingSystem.IsWindows()) Assert.Skip("Windows junction test.");
        var sibling = _root + "-sibling";
        Directory.CreateDirectory(sibling);
        var outside = Path.Combine(sibling, "ownership.db");
        File.WriteAllText(outside, "outside");
        var command = new ProcessStartInfo(Path.Combine(Environment.SystemDirectory, "cmd.exe"))
        { UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true, RedirectStandardError = true };
        foreach (var argument in new[] { "/c", "mklink", "/J", DirectoryPath, sibling }) command.ArgumentList.Add(argument);
        try
        {
            using var process = Process.Start(command)!;
            await process.WaitForExitAsync(TestContext.Current.CancellationToken);
            Assert.Equal(0, process.ExitCode);
            Assert.Throws<ThemeConflictException>(() => _ownership.Find(Guid.NewGuid()));
            Assert.Throws<ThemeConflictException>(() => _ownership.Record(Guid.NewGuid(), "theme.m4a", "digest", () => { }));
            Assert.Equal("outside", File.ReadAllText(outside));
        }
        finally
        {
            if (Directory.Exists(DirectoryPath)) Directory.Delete(DirectoryPath);
            Directory.Delete(sibling, true);
        }
    }
}
