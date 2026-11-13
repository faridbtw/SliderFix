# SliderFix

Alert-slider compatibility fix for **OnePlus 13 PJZ110 / NimarkoOS**, based on PixelOS Android 17 (`PixelOS_dodge-17.0-20260912-0510`). This repository contains only the patch and its build inputs. ROM images, original APKs, compiled payloads, logs and signing keys are excluded.

## What breaks

The kernel exposes the hall slider as `oplus,hall_tri_state_key`, generating Linux `KEY_F3` events. Android InputReader merges it with the fingerprint input because their device identifiers match. The resulting Java input device is named `oplus_fp_input`.

The original Lineage-style `KeyHandler` only accepts the two standalone slider device names. It therefore ignores the real slider events from the merged device. InputReader's device-merging logic is documented in [AOSP InputReader.cpp](https://android.googlesource.com/platform/frameworks/native/+/refs/heads/main/services/inputflinger/reader/InputReader.cpp).

## The patch

The patched `handleKeyEvent` retains the original standalone slider names and additionally accepts **KEYCODE_F3 (133) key-down events from `oplus_fp_input`**. Other events pass through. A null input device is also passed through safely.

The existing `populateKeyState`, `/proc/tristatekey/tri_state` reader, user preferences, Silent/Vibrate/Ring actions, DND behavior and UI are retained. The patch changes no kernel code or global input mapping.

The companion JAR is loaded by a static framework resource overlay. The original installed, signed `KeyHandler.apk` is preserved for package identity, resources, settings and the SystemUI plugin. The overlay keeps the existing TouchGestures handler as the second entry.

Review [the method diff](patches/merged-slider.patch) or [the patched method](patches/handleKeyEvent-patched.smali).

## Build locally

Requirements: Python 3.9+, Java 17+, Apktool 2.12.1, Android SDK Build Tools 36.0.0 and these files from your matching ROM:

- `/system_ext/app/KeyHandler/KeyHandler.apk`
- `/system/framework/framework-res.apk`

```sh
python3 build.py \
  --keyhandler inputs/KeyHandler.apk \
  --framework-res inputs/framework-res.apk \
  --apktool /path/to/apktool.jar \
  --build-tools /path/to/android-sdk/build-tools/36.0.0 \
  --out out
```

`--java /path/to/java` can select a specific runtime. The tool refuses unknown handler implementations and existing output directories. It produces:

- `out/nimarko-slider.jar`
- `out/NimarkoSliderOverlay-unsigned.apk`

Sign the overlay with your ROM or dedicated overlay key. No platform signing key is needed for the companion JAR, and the original installed KeyHandler APK is never re-signed. For example, after creating your own signing keystore:

```sh
apksigner sign --ks /path/to/overlay-signing.jks \
  --out out/NimarkoSliderOverlay.apk \
  out/NimarkoSliderOverlay-unsigned.apk
```

## Include in the ROM

Place the outputs in the **system_ext** image:

| Image-relative path | Owner | Mode | SELinux label |
| --- | --- | --- | --- |
| `/framework/nimarko-slider.jar` | `0:0` | `0644` | `u:object_r:system_file:s0` |
| `/overlay/NimarkoSliderOverlay.apk` | `0:0` | `0644` | `u:object_r:system_file:s0` |

Keep the original KeyHandler APK and TouchGestures APK in place. The overlay replaces the two `config_deviceKeyHandler*` arrays, so its paths must match the device. On the tested guest, default partition order places `system_ext` above the existing vendor overlay. ROMs with a custom overlay config may require explicitly enabling the new overlay there.

Validate overlay policy on a matching device with `idmap2` and validate the image filesystem before packaging. Use your normal DSU packaging process and let the user perform installation and reboot. This repository does not install, flash, reboot, restart the Android framework, weaken SELinux or change boot partitions. Packaged runtime operation does not need KernelSU/KowsuPro.

## Validation and limits

On the running PJZ110 guest, an isolated call showed the original handler rejecting an F3 event from the merged device. The patched handler accepted it and changed Vibrate to Normal for physical position 3. An unrelated F1 event remained unconsumed. The overlay passed `idmap2` checks with system/public policies, and the modified ext4 image passed `e2fsck`. Packaged image members passed CRC and SHA-256 readback checks; no separate checksum files are generated.

The assembled DSU builds have **not been cold-boot tested**. This is not a claim of support for every OnePlus model, kernel, ROM or input-device grouping order. If your merged device has a different name or key code, inspect its events and adapt the filter rather than accepting all fingerprint keys.

An earlier diagnostic restart of the guest Android framework triggered its RescueParty recovery path. Restarting system_server is not a test or installation step for this fix.

The smali reference method was disassembled from the user's original Lineage-style KeyHandler. Full upstream application sources and binaries are not redistributed here; existing upstream rights remain with their respective authors.
