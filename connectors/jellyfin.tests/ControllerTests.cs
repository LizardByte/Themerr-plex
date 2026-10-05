using System.Reflection;
using MediaBrowser.Common.Api;
using MediaBrowser.Common.Configuration;
using MediaBrowser.Controller.Entities;
using MediaBrowser.Controller.Entities.Movies;
using MediaBrowser.Controller.Library;
using MediaBrowser.Model.Serialization;
using MediaBrowser.Model.MediaInfo;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Moq;
using Xunit;

namespace Themerr.Connector.Tests;

public sealed class ControllerTests : IDisposable
{
    private readonly string _root = Path.Combine(Path.GetTempPath(), "themerr-controller-test-" + Guid.NewGuid());
    private readonly Mock<ILibraryManager> _library = new();
    private readonly Controller _controller;
    public ControllerTests()
    {
        Directory.CreateDirectory(_root);
        var media = new Mock<IMediaSourceManager>();
        media.Setup(value => value.GetPathProtocol(It.IsAny<string>())).Returns(MediaProtocol.File);
        BaseItem.MediaSourceManager = media.Object;
        BaseItem.LibraryManager = _library.Object;
        _library.Setup(value => value.GetItemList(It.IsAny<InternalItemsQuery>())).Returns([]);
        _controller = new Controller(_library.Object)
        { ControllerContext = new ControllerContext { HttpContext = new DefaultHttpContext() } };
    }
    public void Dispose() => Directory.Delete(_root, true);

    [Fact]
    public void EndpointsRequireAnAdministrator()
    {
        var policy = typeof(Controller).GetCustomAttribute<AuthorizeAttribute>();
        Assert.Equal(Policies.RequiresElevation, policy?.Policy);
        Assert.Empty(typeof(Controller).GetMethods().SelectMany(method => method.GetCustomAttributes<AllowAnonymousAttribute>()));
    }

    [Fact]
    public void IdentityReportsEmbeddedBuildAndAbi()
    {
        var value = _controller.Identity();
        Assert.Equal(1, value.GetType().GetProperty("protocol")!.GetValue(value));
        Assert.Equal("development", value.GetType().GetProperty("build")!.GetValue(value));
        Assert.Equal(typeof(Plugin).Assembly.GetCustomAttributes<AssemblyMetadataAttribute>()
            .Single(attribute => attribute.Key == "JellyfinAbi").Value,
            value.GetType().GetProperty("targetAbi")!.GetValue(value));
    }

    [Fact]
    public void PluginHasStableIdentityAndNoBackgroundProcessing()
    {
        var paths = new Mock<IApplicationPaths>();
        paths.SetupGet(value => value.PluginsPath).Returns(_root);
        paths.SetupGet(value => value.PluginConfigurationsPath).Returns(_root);
        var plugin = new Plugin(paths.Object, Mock.Of<IXmlSerializer>());
        Assert.Equal("Themerr Connector", plugin.Name);
        Assert.Equal(new Guid("f9a117dc-b44a-4507-9706-241837784369"), plugin.Id);
        Assert.Contains("connector", plugin.Description);
    }

    [Fact]
    public async Task UnknownIdsNeverAccessTheFilesystem()
    {
        Assert.IsType<NotFoundResult>(_controller.State(Guid.NewGuid()).Result);
        _controller.Request.Headers["X-Themerr-Connector"] = "development";
        Assert.IsType<NotFoundResult>((await _controller.Upload(Guid.NewGuid(), CancellationToken.None)).Result);
        Assert.Empty(Directory.GetFiles(_root));
    }

    [Fact]
    public async Task UploadRejectsWrongBuildBeforeResolvingAnItem()
    {
        _controller.Request.Headers["X-Themerr-Connector"] = "different";
        Assert.IsType<ConflictResult>((await _controller.Upload(Guid.NewGuid(), CancellationToken.None)).Result);
        _library.Verify(value => value.GetItemById(It.IsAny<Guid>()), Times.Never);
    }

    [Fact]
    public void CollectionsUseTheirNativeMetadataDirectory()
    {
        var id = Guid.NewGuid();
        _library.Setup(value => value.GetItemById(id)).Returns(new BoxSet { Id = id, Path = _root });
        var result = _controller.State(id);
        Assert.Null(result.Result);
        Assert.False(result.Value!.Present);
    }

    [Fact]
    public async Task LockedAndUnsupportedItemsAreRejected()
    {
        var id = Guid.NewGuid();
        _controller.Request.Headers["X-Themerr-Connector"] = "development";
        _library.Setup(value => value.GetItemById(id)).Returns(new BoxSet { Id = id, Path = _root, IsLocked = true });
        Assert.IsType<ConflictResult>((await _controller.Upload(id, CancellationToken.None)).Result);
        _library.Setup(value => value.GetItemById(id)).Returns(new Folder { Id = id, Path = _root });
        Assert.IsType<BadRequestResult>(_controller.State(id).Result);
        Assert.IsType<ConflictResult>((await _controller.Upload(id, CancellationToken.None)).Result);
    }

    [Fact]
    public async Task InvalidAndProtectedBodiesReturnFixedErrors()
    {
        var id = Guid.NewGuid();
        _library.Setup(value => value.GetItemById(id)).Returns(new BoxSet { Id = id, Path = _root });
        _controller.Request.Headers["X-Themerr-Connector"] = "development";
        Assert.IsType<BadRequestResult>((await _controller.Upload(id, CancellationToken.None)).Result);
        File.WriteAllText(Path.Combine(_root, "theme.mp3"), "user theme");
        _controller.Request.ContentType = "audio/mp4";
        _controller.Request.Headers["X-Themerr-SHA256"] = new string('a', 64);
        Assert.IsType<ConflictResult>((await _controller.Upload(id, CancellationToken.None)).Result);
    }
}
