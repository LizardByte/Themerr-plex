using System.Text.Json.Serialization;

namespace Themerr.Connector;

/// <summary>Describes theme presence and ownership verified against the current audio digest.</summary>
/// <param name="Present">Whether Jellyfin or the filesystem reports a theme.</param>
/// <param name="Owned">Whether a single theme matches its connector ownership record.</param>
/// <param name="Sha256">The tracked theme's current SHA-256 digest, or null when ambiguous.</param>
public sealed record class ThemeState(
    bool Present,
    bool Owned,
    string? Sha256)
{
    /// <summary>Gets a value indicating whether Jellyfin or the filesystem reports a theme.</summary>
    [JsonPropertyName("present")]
    public bool Present { get; init; } = Present;

    /// <summary>Gets a value indicating whether the theme matches the connector's ownership record.</summary>
    [JsonPropertyName("owned")]
    public bool Owned { get; init; } = Owned;

    /// <summary>Gets the current digest, or null when theme ownership is ambiguous.</summary>
    [JsonPropertyName("sha256")]
    public string? Sha256 { get; init; } = Sha256;
}
