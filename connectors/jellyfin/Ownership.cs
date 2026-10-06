namespace Themerr.Connector;

/// <summary>Holds the fixed filename and digest of a connector-owned theme.</summary>
/// <param name="File">A filename selected from the code-owned theme name list.</param>
/// <param name="Sha256">The theme's lowercase SHA-256 digest.</param>
public sealed record class Ownership(string File, string Sha256)
{
    /// <summary>Gets the fixed theme filename.</summary>
    public string File { get; init; } = File;

    /// <summary>Gets the theme's lowercase SHA-256 digest.</summary>
    public string Sha256 { get; init; } = Sha256;
}
