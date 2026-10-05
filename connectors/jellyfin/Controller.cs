using System.Collections.Concurrent;
using System.Reflection;
using MediaBrowser.Common.Api;
using MediaBrowser.Controller.Entities;
using MediaBrowser.Controller.Library;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace Themerr.Connector;

[ApiController]
[Route("Themerr")]
[Authorize(Policy = Policies.RequiresElevation)]
public sealed class Controller : ControllerBase
{
    private static readonly ConcurrentDictionary<Guid, SemaphoreSlim> Locks = new();
    private readonly ILibraryManager _library;
    private static string Metadata(string key) => typeof(Plugin).Assembly.GetCustomAttributes<AssemblyMetadataAttribute>()
        .Single(a => a.Key == key).Value!;

    public Controller(ILibraryManager library) => _library = library;

    [HttpGet("Connector")]
    public object Identity() => new { protocol = 1, build = Metadata("ThemerrBuild"), targetAbi = Metadata("JellyfinAbi") };

    [HttpGet("Items/{itemId:guid}/Theme")]
    public ActionResult<ThemeState> State(Guid itemId)
    {
        var item = _library.GetItemById(itemId);
        if (item is null) return NotFound();
        var root = Root(item);
        if (root is null) return BadRequest();
        return ThemeFiles.State(root, item.GetThemeSongs().Count);
    }

    [HttpPost("Items/{itemId:guid}/Theme")]
    [RequestSizeLimit(104857600)]
    public async Task<ActionResult<ThemeState>> Upload(Guid itemId, CancellationToken cancellationToken)
    {
        if (Request.Headers["X-Themerr-Connector"] != Metadata("ThemerrBuild")) return Conflict();
        var item = _library.GetItemById(itemId);
        if (item is null) return NotFound();
        var root = Root(item);
        if (root is null || (item.IsLocked && Request.Headers["X-Themerr-Ignore-Locked"] != "true")) return Conflict();
        var gate = Locks.GetOrAdd(itemId, _ => new SemaphoreSlim(1, 1));
        await gate.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            var state = await ThemeFiles.Save(root, Request.Body, Request.ContentType,
                Request.Headers["X-Themerr-SHA256"].ToString(), item.GetThemeSongs().Count,
                cancellationToken).ConfigureAwait(false);
            await item.RefreshMetadata(cancellationToken).ConfigureAwait(false);
            return state;
        }
        catch (ThemeConflictException) { return Conflict(); }
        catch (InvalidDataException) { return BadRequest(); }
        catch (IOException) { return StatusCode(500); }
        catch (UnauthorizedAccessException) { return StatusCode(500); }
        finally { gate.Release(); }
    }

    private static string? Root(BaseItem item) =>
        item is MediaBrowser.Controller.Entities.Movies.Movie or MediaBrowser.Controller.Entities.TV.Series or
            MediaBrowser.Controller.Entities.Movies.BoxSet &&
        item.IsFileProtocol && !item.IsInMixedFolder && Directory.Exists(item.ContainingFolderPath)
            ? Path.GetFullPath(item.ContainingFolderPath) : null;
}
