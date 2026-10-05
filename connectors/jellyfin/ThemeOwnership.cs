using Microsoft.Data.Sqlite;
using System.Collections.Concurrent;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.EntityFrameworkCore.Migrations;

namespace Themerr.Connector;

public sealed record Ownership(string File, string Sha256);

/// <summary>Stores ownership in one database beneath Jellyfin's trusted server data directory.</summary>
public sealed class ThemeOwnership
{
    private static readonly ConcurrentDictionary<string, object> Gates = new(StringComparer.Ordinal);
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
        using var context = Open(SqliteOpenMode.ReadOnly);
        var id = itemId.ToString("N");
        var entry = context.Themes.AsNoTracking().SingleOrDefault(value => value.ItemId == id);
        return entry is null ? null : new(entry.File, entry.Sha256);
    }

    public void Record(Guid itemId, string file, string digest, Action writeTheme)
    {
        lock (Gates.GetOrAdd(_database, _ => new object()))
        {
            ValidatePaths();
            Directory.CreateDirectory(_directory);
            using var context = Open(SqliteOpenMode.ReadWriteCreate);
            Migrate(context);
            // Acquire the database write lock before changing audio; failures roll back ownership.
            using var transaction = context.Database.BeginTransaction();
            var id = itemId.ToString("N");
            var entry = context.Themes.Find(id);
            if (entry is null)
            {
                entry = new OwnershipEntry { ItemId = id };
                context.Themes.Add(entry);
            }
            entry.File = file;
            entry.Sha256 = digest;
            context.SaveChanges();
            writeTheme();
            transaction.Commit();
        }
    }

    private static void Migrate(OwnershipContext context)
    {
        var history = context.GetService<IHistoryRepository>();
        if (!history.GetAppliedMigrations().Any())
        {
            var existing = false;
            try { context.Themes.AsNoTracking().Take(1).ToList(); existing = true; }
            catch (SqliteException error) when (error.SqliteErrorCode == 1) { }
            if (existing)
            {
                // Adopt the connector's original SQLite schema using EF-generated history commands.
                // No rows are copied, discarded, or rebuilt.
                using var transaction = context.Database.BeginTransaction();
                context.Database.ExecuteSqlRaw(history.GetCreateIfNotExistsScript());
                context.Database.ExecuteSqlRaw(history.GetInsertScript(new HistoryRow(
                    InitialOwnership.Id, typeof(DbContext).Assembly.GetName().Version!.ToString())));
                transaction.Commit();
            }
        }
        context.Database.Migrate();
    }

    private OwnershipContext Open(SqliteOpenMode mode)
    {
        ValidatePaths();
        var connection = new SqliteConnectionStringBuilder
        {
            DataSource = _database, Mode = mode, Pooling = false
        }.ToString();
        return new OwnershipContext(new DbContextOptionsBuilder<OwnershipContext>().UseSqlite(connection).Options);
    }

    private void ValidatePaths() => ValidateDatabase(_directory, _database);

    internal static void ValidateDatabase(string root, string database)
    {
        var directory = new DirectoryInfo(root);
        if (directory.LinkTarget is not null ||
            (directory.Exists && (directory.Attributes & FileAttributes.ReparsePoint) != 0))
            throw new ThemeConflictException();
        // SQLite can create these fixed companion files while a transaction is in progress.
        foreach (var path in new[] { database, database + "-journal", database + "-wal", database + "-shm" })
        {
            var info = new FileInfo(path);
            if (info.LinkTarget is not null || (info.Exists && (info.Attributes & FileAttributes.ReparsePoint) != 0))
                throw new ThemeConflictException();
        }
    }
}
