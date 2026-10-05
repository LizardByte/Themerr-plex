using Microsoft.EntityFrameworkCore;

namespace Themerr.Connector;

/// <summary>Maps the connector's verified upload ownership records to SQLite.</summary>
/// <seealso cref="OwnershipEntry"/>
public sealed class OwnershipContext : DbContext
{
    /// <summary>Initializes a new instance of the <see cref="OwnershipContext"/> class.</summary>
    /// <param name="options">The fixed SQLite connection and EF provider settings.</param>
    public OwnershipContext(DbContextOptions<OwnershipContext> options)
        : base(options)
    {
    }

    /// <summary>Gets the ownership rows indexed by native Jellyfin item ID.</summary>
    public DbSet<OwnershipEntry> Themes => Set<OwnershipEntry>();

    /// <summary>Configures the fixed ownership table and required columns.</summary>
    /// <param name="modelBuilder">EF's model definition builder.</param>
    internal static void ConfigureModel(ModelBuilder modelBuilder)
    {
        var entry = modelBuilder.Entity<OwnershipEntry>();
        entry.ToTable("theme_ownership");
        entry.HasKey(value => value.ItemId);
        entry.Property(value => value.ItemId).HasColumnName("item_id").HasColumnType("TEXT").IsRequired();
        entry.Property(value => value.File).HasColumnName("filename").HasColumnType("TEXT").IsRequired();
        entry.Property(value => value.Sha256).HasColumnName("sha256").HasColumnType("TEXT").IsRequired();
    }

    /// <summary>Builds the ownership model using the shared migration definition.</summary>
    /// <param name="modelBuilder">EF's model definition builder.</param>
    protected override void OnModelCreating(ModelBuilder modelBuilder) => ConfigureModel(modelBuilder);
}
