namespace Themerr.Connector;

/// <summary>Maps only the older plugin columns needed to verify theme ownership.</summary>
public sealed class LegacyTheme
{
    /// <summary>Gets or sets the native item ID in compact or hyphenated UUID form.</summary>
    public string? ItemId { get; set; }

    /// <summary>Gets or sets the older plugin's recorded theme digest.</summary>
    public string? ThemeHash { get; set; }

    /// <summary>Gets or sets the hash algorithm; only SHA256 records are recognized.</summary>
    public string? ThemeHashAlgorithm { get; set; }

    /// <summary>Gets or sets the provider; only Themerr-owned records are recognized.</summary>
    public string? ThemeProvider { get; set; }
}
