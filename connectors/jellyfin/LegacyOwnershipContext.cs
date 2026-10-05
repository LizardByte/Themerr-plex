using Microsoft.EntityFrameworkCore;

namespace Themerr.Connector;

/// <summary>Reads the older plugin's table without migrations or database mutations.</summary>
public sealed class LegacyOwnershipContext : DbContext
{
    /// <summary>Initializes a new instance of the <see cref="LegacyOwnershipContext"/> class.</summary>
    /// <param name="options">The read-only SQLite connection settings.</param>
    public LegacyOwnershipContext(DbContextOptions<LegacyOwnershipContext> options)
        : base(options)
    {
    }

    /// <summary>Gets the legacy ownership rows without assuming a unique database key.</summary>
    public DbSet<LegacyTheme> Themes => Set<LegacyTheme>();

    /// <summary>Maps only the known columns from the older plugin's media table.</summary>
    /// <param name="modelBuilder">EF's model definition builder.</param>
    protected override void OnModelCreating(ModelBuilder modelBuilder) =>
        modelBuilder.Entity<LegacyTheme>().HasNoKey().ToTable("ThemerrMediaItems");
}
