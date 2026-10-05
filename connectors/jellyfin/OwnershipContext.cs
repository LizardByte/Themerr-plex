using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.EntityFrameworkCore.Migrations;

namespace Themerr.Connector;

public sealed class OwnershipEntry
{
    public string ItemId { get; set; } = "";
    public string File { get; set; } = "";
    public string Sha256 { get; set; } = "";
}

public sealed class OwnershipContext(DbContextOptions<OwnershipContext> options) : DbContext(options)
{
    public DbSet<OwnershipEntry> Themes => Set<OwnershipEntry>();
    protected override void OnModelCreating(ModelBuilder modelBuilder) => ConfigureModel(modelBuilder);

    internal static void ConfigureModel(ModelBuilder modelBuilder)
    {
        var entry = modelBuilder.Entity<OwnershipEntry>();
        entry.ToTable("theme_ownership");
        entry.HasKey(value => value.ItemId);
        entry.Property(value => value.ItemId).HasColumnName("item_id").HasColumnType("TEXT").IsRequired();
        entry.Property(value => value.File).HasColumnName("filename").HasColumnType("TEXT").IsRequired();
        entry.Property(value => value.Sha256).HasColumnName("sha256").HasColumnType("TEXT").IsRequired();
    }
}

[DbContext(typeof(OwnershipContext))]
[Migration(InitialOwnership.Id)]
public sealed class InitialOwnership : Migration
{
    internal const string Id = "202610050001_InitialOwnership";
    protected override void Up(MigrationBuilder migrationBuilder) => migrationBuilder.CreateTable(
        name: "theme_ownership",
        columns: table => new
        {
            item_id = table.Column<string>(type: "TEXT", nullable: false),
            filename = table.Column<string>(type: "TEXT", nullable: false),
            sha256 = table.Column<string>(type: "TEXT", nullable: false)
        },
        constraints: table => table.PrimaryKey("PK_theme_ownership", value => value.item_id));

    protected override void Down(MigrationBuilder migrationBuilder) => migrationBuilder.DropTable("theme_ownership");
    protected override void BuildTargetModel(ModelBuilder modelBuilder) => OwnershipContext.ConfigureModel(modelBuilder);
}

[DbContext(typeof(OwnershipContext))]
public sealed class OwnershipModelSnapshot : ModelSnapshot
{
    protected override void BuildModel(ModelBuilder modelBuilder) => OwnershipContext.ConfigureModel(modelBuilder);
}
