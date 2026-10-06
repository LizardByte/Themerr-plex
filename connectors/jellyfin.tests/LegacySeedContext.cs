using Microsoft.EntityFrameworkCore;

namespace Themerr.Connector.Tests;

/// <summary>Creates an independent fixture matching the older plugin database.</summary>
/// <param name="options">The fixture database connection and provider settings.</param>
public sealed class LegacySeedContext(DbContextOptions<LegacySeedContext> options) : DbContext(options)
{
    /// <summary>Gets the legacy schema rows used to seed ownership fixtures.</summary>
    public DbSet<LegacyRow> Themes => Set<LegacyRow>();

    /// <inheritdoc/>
    protected override void OnModelCreating(ModelBuilder modelBuilder) => modelBuilder.Entity<LegacyRow>().ToTable("ThemerrMediaItems");
}
