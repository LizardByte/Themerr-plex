using MediaBrowser.Common.Configuration;
using MediaBrowser.Common.Plugins;
using MediaBrowser.Model.Plugins;
using MediaBrowser.Model.Serialization;

namespace Themerr.Connector;

/// <summary>Only exposes authenticated theme upload; Themerr owns all processing.</summary>
public sealed class Plugin : BasePlugin<BasePluginConfiguration>
{
    public Plugin(IApplicationPaths paths, IXmlSerializer serializer) : base(paths, serializer) { }
    public override string Name => "Themerr Connector";
    public override string Description => "Theme upload connector for a matching Themerr installation.";
    public override Guid Id => new("f9a117dc-b44a-4507-9706-241837784369");
}
