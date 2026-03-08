---
description: Research UE 5.7 source to validate this repo's API usage and patterns
---

# Unreal Engine Source Research

Cross-reference this repository's C++ code against the Unreal Engine source to verify correct API usage and identify best-practice improvements.

## Scope

The user may optionally provide a focus area: $ARGUMENTS

If a focus area is given (e.g. a file path, class name, module name, or topic like "depth capture" or "Mass Entity"), narrow the research to that area. Otherwise, research the full codebase.

## Setup

Read `config.toml` and find the `ue_source_path` under `[plugin-config.ue]`. If it is empty or not set, tell the user they need to configure it first (point them to the README's UE Plugin section or run `/setup-ue`).

## Repository Source Locations

Auto-discover source locations in this repository:
1. Search for all `*.uproject` files to identify project roots
2. Search for all `*.Build.cs` files to identify modules
3. Search for all `Source/` directories that contain `.h` or `.cpp` files
4. List what you found before proceeding

## UE Source Location

Read from `ue_source_path` in config. Key areas to cross-reference:
- `Runtime/` - core engine APIs, rendering, scene management
- `Runtime/Engine/` - UObject, AActor, UWorld, components
- `Runtime/Core/` - containers, math, delegates, logging
- `Runtime/RenderCore/` - render thread, RHI utilities
- `Runtime/Renderer/` - deferred/forward rendering, scene proxies
- `Runtime/RHI/` - render hardware interface
- `Runtime/MassEntity/` - Mass Entity framework (ECS)
- `Editor/` - editor APIs, commandlets, validation
- `Programs/UnrealBuildTool/` - build system, module rules

## Research Process

Use parallel subagents to speed up the research. For each source file or module in this repo:

### 1. Identify APIs Used
Read the repo's source files in the focus area. Extract:
- UE base classes inherited from
- UE functions/methods called
- UE macros used (UCLASS, UPROPERTY, UFUNCTION, etc.)
- Module dependencies in .Build.cs files
- #include paths referencing engine headers

### 2. Cross-Reference Against UE Source
For each API identified, search the UE source to verify:
- **API existence**: Does the class/function/macro still exist?
- **Signature changes**: Has the function signature changed?
- **Deprecation**: Look for UE_DEPRECATED, DEPRECATED(), or [[deprecated]] markers
- **Replacement APIs**: If deprecated, what is the recommended replacement?
- **Module changes**: Have any modules been renamed, merged, or split?

### 3. Check Best Practice Patterns
Compare implementation patterns against current UE conventions:
- Smart pointers (TSharedPtr/TWeakObjectPtr/TObjectPtr)
- Property specifiers (UPROPERTY/UFUNCTION)
- Async patterns
- Rendering pipeline (RDG patterns vs legacy)
- Mass Entity fragment and processor patterns
- Enhanced Input patterns
- World Partition / HLOD
- Subsystem patterns

### 4. Check Build Configuration
Review .Build.cs files for:
- Deprecated module names or references
- Missing recommended modules
- Build settings against current defaults

## Output Format

### API Compatibility Issues
| File | API/Symbol | Status | Details |
|------|-----------|--------|---------|
| ... | ... | Deprecated / Removed / Changed | ... |

### Best Practice Recommendations
- **What**: Current code pattern
- **Where**: File and line number
- **Why**: What changed or why suboptimal
- **Recommendation**: Specific change with code reference

### Build Configuration Issues
Any .Build.cs problems found.

### Summary
- Total files analyzed
- Critical issues (broken/removed APIs)
- Warnings (deprecated APIs still functional)
- Suggestions (best practice improvements)
