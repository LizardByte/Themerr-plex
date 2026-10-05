using Microsoft.Data.Sqlite;
using Microsoft.EntityFrameworkCore;

namespace Themerr.Connector;

public sealed class LegacyTheme
{
    public string? ItemId { get; set; }
    public string? ThemeHash { get; set; }
    public string? ThemeHashAlgorithm { get; set; }
    public string? ThemeProvider { get; set; }
}

public sealed class LegacyOwnershipContext(DbContextOptions<LegacyOwnershipContext> options) : DbContext(options)
{
    public DbSet<LegacyTheme> Themes => Set<LegacyTheme>();
    protected override void OnModelCreating(ModelBuilder modelBuilder) =>
        modelBuilder.Entity<LegacyTheme>().HasNoKey().ToTable("ThemerrMediaItems");
}

/// <summary>Reads only verified ownership from the old plugin's fixed database, without migrating it.</summary>
public sealed class LegacyOwnership(string serverDataPath)
{
    public string? Hash(Guid itemId)
    {
        var directory = Path.Combine(serverDataPath, "Themerr");
        var database = Path.Combine(directory, "themerr.db");
        ThemeOwnership.ValidateDatabase(directory, database);
        if (!File.Exists(database)) return null;
        var connection = new SqliteConnectionStringBuilder
            { DataSource = database, Mode = SqliteOpenMode.ReadOnly, Pooling = false }.ToString();
        using var context = new LegacyOwnershipContext(
            new DbContextOptionsBuilder<LegacyOwnershipContext>().UseSqlite(connection).Options);
        var compact = itemId.ToString("N");
        var standard = itemId.ToString("D");
        var rows = context.Themes.AsNoTracking().Where(value => value.ItemId == compact || value.ItemId == standard)
            .Take(2).ToList();
        return rows.Count == 1 && rows[0].ThemeProvider == "themerr" && rows[0].ThemeHashAlgorithm == "SHA256"
            ? rows[0].ThemeHash : null;
    }
}
