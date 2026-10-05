namespace Themerr.Connector.Tests;

/// <summary>Represents the older plugin schema used to seed import fixtures.</summary>
public sealed class LegacyRow
{
    /// <summary>Gets or sets the older plugin's row key.</summary>
    public int Id { get; set; }

    /// <summary>Gets or sets the native Jellyfin item identifier.</summary>
    public string ItemId { get; set; } = string.Empty;

    /// <summary>Gets or sets the recorded theme digest.</summary>
    public string ThemeHash { get; set; } = string.Empty;

    /// <summary>Gets or sets the recorded hash algorithm.</summary>
    public string ThemeHashAlgorithm { get; set; } = "SHA256";

    /// <summary>Gets or sets the provider that created the original theme.</summary>
    public string ThemeProvider { get; set; } = "themerr";

    /// <summary>Gets or sets a hostile recorded path that must never be used for file access.</summary>
    public string ThemePath { get; set; } = "../../untrusted.mp3";
}
