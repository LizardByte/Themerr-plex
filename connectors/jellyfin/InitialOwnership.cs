using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.EntityFrameworkCore.Migrations;

namespace Themerr.Connector;

/// <summary>Creates the connector's item ownership table without storing audio in SQLite.</summary>
[DbContext(typeof(OwnershipContext))]
[Migration(InitialOwnership.Id)]
public sealed class InitialOwnership : Migration
{
    /// <summary>The stable identifier of the initial ownership schema.</summary>
    internal const string Id = "202610050001_InitialOwnership";

    /// <summary>Creates required ownership columns and the native item ID primary key.</summary>
    /// <param name="migrationBuilder">EF's schema operation builder.</param>
    protected override void Up(MigrationBuilder migrationBuilder) => migrationBuilder.CreateTable(
        name: "theme_ownership",
        columns: table => new
        {
            item_id = table.Column<string>(type: "TEXT", nullable: false),
            filename = table.Column<string>(type: "TEXT", nullable: false),
            sha256 = table.Column<string>(type: "TEXT", nullable: false),
        },
        constraints: table => table.PrimaryKey("PK_theme_ownership", value => value.item_id));

    /// <summary>Removes the ownership table when explicitly rolling back this migration.</summary>
    /// <param name="migrationBuilder">EF's schema operation builder.</param>
    protected override void Down(MigrationBuilder migrationBuilder) => migrationBuilder.DropTable("theme_ownership");

    /// <summary>Describes the model produced by the initial migration.</summary>
    /// <param name="modelBuilder">EF's model definition builder.</param>
    protected override void BuildTargetModel(ModelBuilder modelBuilder) => OwnershipContext.ConfigureModel(modelBuilder);
}
