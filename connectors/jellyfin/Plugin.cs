using MediaBrowser.Common.Configuration;
using MediaBrowser.Common.Plugins;
using MediaBrowser.Model.Plugins;
using MediaBrowser.Model.Serialization;

namespace Themerr.Connector;

/// <summary>
/// Identifies the administrator-only connector; Themerr owns downloading and scheduling.
/// </summary>
/// <seealso cref="Controller"/>
public sealed class Plugin : BasePlugin<BasePluginConfiguration>
{
    /// <summary>
    /// Initializes a new instance of the <see cref="Plugin"/> class.
    /// </summary>
    /// <param name="paths">Jellyfin's trusted application directories.</param>
    /// <param name="serializer">Jellyfin's plugin configuration serializer.</param>
    public Plugin(IApplicationPaths paths, IXmlSerializer serializer)
        : base(paths, serializer)
    {
    }

    /// <summary>Gets the name displayed in Jellyfin's plugin catalog.</summary>
    public override string Name => "Themerr Connector";

    /// <summary>Gets the connector's role in the Themerr integration.</summary>
    public override string Description => "Theme upload connector for a matching Themerr installation.";

    /// <summary>Gets the stable identifier used for installation and replacement.</summary>
    public override Guid Id => new("f9a117dc-b44a-4507-9706-241837784369");
}
