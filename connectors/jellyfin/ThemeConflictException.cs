namespace Themerr.Connector;

/// <summary>Signals a protected, unsafe, or concurrently changed theme resource.</summary>
/// <seealso cref="ThemeFiles"/>
public sealed class ThemeConflictException : Exception
{
}
