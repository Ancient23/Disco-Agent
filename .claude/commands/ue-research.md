---
description: Research UE 5.7 source to validate this repo's API usage and patterns
---

# Unreal Engine 5.7 Research

Cross-reference this repository's C++ code against the Unreal Engine 5.7.3 source at `C:/Source/UnrealEngine` to verify correct API usage and identify best-practice improvements.

## Scope

The user may optionally provide a focus area: $ARGUMENTS

If a focus area is given (e.g. a file path, class name, module name, or topic like "depth capture" or "Mass Entity"), narrow the research to that area. Otherwise, research the full codebase.

## Repository Source Locations

- **Custom plugin**: `Plugins/ImpGameCap4D/Source/`
- **CitySample project**: `Proj/CitySample/Source/`
- **CitySample plugins**: `Proj/CitySample/Plugins/*/Source/`
- **Lumen4DCapSamp project**: `Proj/Lumen4DCapSamp/Source/`
- **Build configs**: `*.Build.cs` files in the above paths

## UE 5.7 Source Location

`C:/Source/UnrealEngine/Engine/Source/`

Key areas to cross-reference:
- `Runtime/` - core engine APIs, rendering, scene management
- `Runtime/Engine/` - UObject, AActor, UWorld, components
- `Runtime/Core/` - containers, math, delegates, logging
- `Runtime/RenderCore/` - render thread, RHI utilities
- `Runtime/Renderer/` - deferred/forward rendering, scene proxies
- `Runtime/RHI/` - render hardware interface
- `Runtime/MassEntity/` - Mass Entity framework (ECS)
- `Runtime/SceneCapture/` - scene capture components
- `Editor/` - editor APIs, commandlets, validation
- `Programs/UnrealBuildTool/` - build system, module rules

## Research Process

Use parallel subagents to speed up the research. For each source file or module in this repo:

### 1. Identify APIs Used

Read the repo's source files (headers and implementations) in the focus area. Extract:
- UE base classes inherited from (e.g. `AActor`, `USceneComponent`, `FSceneProxy`)
- UE functions/methods called
- UE macros used (`UCLASS`, `UPROPERTY`, `UFUNCTION`, `GENERATED_BODY`, etc.)
- Module dependencies in `.Build.cs` files
- `#include` paths referencing engine headers

### 2. Cross-Reference Against UE 5.7 Source

For each API identified, search the UE source at `C:/Source/UnrealEngine/Engine/Source/` to verify:

- **API existence**: Does the class/function/macro still exist in 5.7? Search headers.
- **Signature changes**: Has the function signature changed (new params, different return types, renamed)?
- **Deprecation**: Look for `UE_DEPRECATED`, `DEPRECATED()`, or `[[deprecated]]` markers on APIs we use.
- **Replacement APIs**: If deprecated, what is the recommended replacement?
- **Module changes**: Have any modules been renamed, merged, or split? Check `.Build.cs` module names against `C:/Source/UnrealEngine/Engine/Source/*/*.Build.cs`.

### 3. Check Best Practice Patterns

Compare our implementation patterns against UE 5.7 conventions:

- **Smart pointers**: Are we using `TSharedPtr`/`TWeakObjectPtr`/`TObjectPtr` correctly per 5.7 conventions?
- **Property specifiers**: Are `UPROPERTY`/`UFUNCTION` specifiers up to date? (e.g. 5.7 may prefer new specifiers)
- **Async patterns**: Are we using current async/task patterns vs deprecated ones?
- **Rendering pipeline**: For any rendering code, verify we use the current RDG (Render Dependency Graph) patterns, not legacy immediate-mode RHI calls.
- **Mass Entity**: If using MassEntity/MassGameplay, verify fragment and processor patterns match 5.7 API.
- **Enhanced Input**: Verify input modifier patterns if applicable.
- **World Partition**: Check any world partition / HLOD code against current APIs.
- **Subsystem patterns**: Verify subsystem usage (UGameInstanceSubsystem, UWorldSubsystem, etc.)

### 4. Check Build Configuration

Review `.Build.cs` files for:
- Deprecated module names or references
- Missing recommended modules for the APIs we use
- `bUseUnity`, `PCHUsage`, and other build settings against 5.7 defaults

## Output Format

Present findings as a structured report:

### API Compatibility Issues
| File | API/Symbol | Status | Details |
|------|-----------|--------|---------|
| ... | ... | Deprecated / Removed / Changed | ... |

### Best Practice Recommendations
For each finding:
- **What**: The current code pattern
- **Where**: File and line number
- **Why**: What changed in UE 5.7 or why the current pattern is suboptimal
- **Recommendation**: The specific change to make, with code snippet from UE 5.7 source as reference

### Build Configuration Issues
Any `.Build.cs` problems found.

### Summary
- Total files analyzed
- Critical issues (broken/removed APIs)
- Warnings (deprecated APIs still functional)
- Suggestions (best practice improvements)
