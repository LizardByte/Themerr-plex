namespace Themerr.Connector;

/// <summary>Stores one item's uploaded theme filename and verified content digest.</summary>
public sealed class OwnershipEntry
{
    /// <summary>Gets or sets the native Jellyfin item ID without UUID separators.</summary>
    public string ItemId { get; set; } = string.Empty;

    /// <summary>Gets or sets a filename selected from the fixed theme name list.</summary>
    public string File { get; set; } = string.Empty;

    /// <summary>Gets or sets the uploaded theme's lowercase SHA-256 digest.</summary>
    public string Sha256 { get; set; } = string.Empty;
}
