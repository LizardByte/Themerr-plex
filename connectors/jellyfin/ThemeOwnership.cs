using Microsoft.Data.Sqlite;

namespace Themerr.Connector;

public sealed record Ownership(string File, string Sha256);

/// <summary>Stores ownership in one database beneath Jellyfin's trusted server data directory.</summary>
public sealed class ThemeOwnership
{
    private readonly string _directory;
    private readonly string _database;

    public ThemeOwnership(string serverDataPath)
    {
        _directory = Path.Combine(serverDataPath, "themerr-connector");
        _database = Path.Combine(_directory, "ownership.db");
    }

    public Ownership? Find(Guid itemId)
    {
        ValidatePaths();
        if (!File.Exists(_database)) return null;
        using var connection = Open(SqliteOpenMode.ReadOnly);
        using var command = connection.CreateCommand();
        command.CommandText = "SELECT filename, sha256 FROM theme_ownership WHERE item_id = $id";
        command.Parameters.AddWithValue("$id", itemId.ToString("N"));
        using var reader = command.ExecuteReader();
        return reader.Read() ? new(reader.GetString(0), reader.GetString(1)) : null;
    }

    public void Record(Guid itemId, string file, string digest, Action writeTheme)
    {
        ValidatePaths();
        Directory.CreateDirectory(_directory);
        using var connection = Open(SqliteOpenMode.ReadWriteCreate);
        using (var schema = connection.CreateCommand())
        {
            schema.CommandText = """
                CREATE TABLE IF NOT EXISTS theme_ownership (
                    item_id TEXT PRIMARY KEY NOT NULL,
                    filename TEXT NOT NULL,
                    sha256 TEXT NOT NULL
                )
                """;
            schema.ExecuteNonQuery();
        }
        // Acquire the database write lock before changing audio; failed writes roll back ownership.
        using var transaction = connection.BeginTransaction();
        using var command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = """
            INSERT INTO theme_ownership (item_id, filename, sha256) VALUES ($id, $file, $digest)
            ON CONFLICT(item_id) DO UPDATE SET filename = excluded.filename, sha256 = excluded.sha256
            """;
        command.Parameters.AddWithValue("$id", itemId.ToString("N"));
        command.Parameters.AddWithValue("$file", file);
        command.Parameters.AddWithValue("$digest", digest);
        command.ExecuteNonQuery();
        writeTheme();
        transaction.Commit();
    }

    private SqliteConnection Open(SqliteOpenMode mode)
    {
        ValidatePaths();
        var connection = new SqliteConnection(new SqliteConnectionStringBuilder
        {
            DataSource = _database, Mode = mode, Pooling = false
        }.ToString());
        try { connection.Open(); }
        catch { connection.Dispose(); throw; }
        return connection;
    }

    private void ValidatePaths()
    {
        var directory = new DirectoryInfo(_directory);
        if (directory.LinkTarget is not null ||
            (directory.Exists && (directory.Attributes & FileAttributes.ReparsePoint) != 0))
            throw new ThemeConflictException();
        // SQLite can create these fixed companion files while a transaction is in progress.
        foreach (var path in new[] { _database, _database + "-journal", _database + "-wal", _database + "-shm" })
        {
            var info = new FileInfo(path);
            if (info.LinkTarget is not null || (info.Exists && (info.Attributes & FileAttributes.ReparsePoint) != 0))
                throw new ThemeConflictException();
        }
    }
}
