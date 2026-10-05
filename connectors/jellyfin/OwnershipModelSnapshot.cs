using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Infrastructure;

namespace Themerr.Connector;

/// <summary>Tracks the ownership model used to detect future EF schema changes.</summary>
[DbContext(typeof(OwnershipContext))]
public sealed class OwnershipModelSnapshot : ModelSnapshot
{
    /// <summary>Builds the fixed ownership schema snapshot.</summary>
    /// <param name="modelBuilder">EF's model definition builder.</param>
    protected override void BuildModel(ModelBuilder modelBuilder) => OwnershipContext.ConfigureModel(modelBuilder);
}
