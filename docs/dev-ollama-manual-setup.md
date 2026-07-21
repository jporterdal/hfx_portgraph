# Phase 1 - manual install of ollama for AMD on WSL2
Recommended approach to installing ollama is to download a .SH file from ollama.com without hash verification and pipe it directly to bash. This is poor security practice.

Running Debian on WSL2 (Windows 11) provides some additional challenges for running ollama as some of the binaries from AMD assume *only* Ubuntu.

The steps herein successfully ran the latest ollama server at time of writing on a Windows 11 machine running Debian on WSL2 and using a Radeon RX 9060 XT GPU.

## Download + verify ollama
Download latest .ZST file and checksum direct from GitHub releases, verify with sha256. Modify release version number as needed.

```
# download asset + published sums
curl -fsSL -O https://github.com/ollama/ollama/releases/download/v0.32.1/ollama-linux-amd64.tar.zst
curl -fsSL -O https://github.com/ollama/ollama/releases/download/v0.32.1/sha256sum.txt

# verify (must be in the same directory)
sha256sum -c sha256sum.txt --ignore-missing
```

## Install zst package
Use apt on Debian.

```
sudo apt update && sudo apt install -y zstd
```

## Manually install ollama
Follows roughly along with "Linux" installation instructions under "Manual Install" but modifying the initial step:
https://docs.ollama.com/linux

 - instead of using curl, skip entirely
 - instead of piping curl's stdout binary stream directly to tar, first inspect file's contents with `tar -tf` (optional) then extract to the same `/usr` location. Architecture here is `amd64` and may (rarely) vary based on system.

```
tar -tf ollama-linux-amd64.tar.zst
sudo tar -xf ollama-linux-amd64.tar.zst -C /usr
```

## Download + install ROCm drivers
For Debian/WSL2 this is more complicated because AMD/ROCm drivers are specifically tuned for Ubuntu.

 (1) Add current user to render,video groups
 ```
 sudo usermod -a -G render,video $LOGNAME
 ```

 (2) Download+install `amdgpu-install` from DEB. Latest version number in filename can vary, check for latest version number here:
 https://repo.radeon.com/amdgpu-install/latest/ubuntu/jammy

 ```
 sudo apt update
 sudo apt install -y wget gnupg2

 wget https://repo.radeon.com/amdgpu-install/latest/ubuntu/jammy/amdgpu-install_7.2.4.70204-1_all.deb
 cp amdgpu-install_7.2.4.70204-1_all.deb /tmp/
 
 sudo apt install /tmp/amdgpu-install_7.2.4.70204-1_all.deb
 sudo apt update
 ```

 (3) Download+install `rocdxg` package, v1.2.0 used below, check URL for updated versions here:
 https://github.com/ROCm/librocdxg/releases

 ```
 wget https://github.com/ROCm/librocdxg/releases/download/v1.2.0/rocdxg-roct_1.2.0_amd64.deb
 sudo dpkg -i rocdxg-roct_1.2.0_amd64.deb
 ```
 
 (4) Update environment variables by appending to `.bashrc` file then reload bash. The `DETECTION=1` variable is documented as *not* being needed, but was anyway on first successful attempt.

 ```
 echo 'export HSA_ENABLE_DXG_DETECTION=1' >> ~/.bashrc
 echo 'export PATH=/opt/rocm/bin:$PATH' >> ~/.bashrc
 echo 'export LD_LIBRARY_PATH=/opt/rocm/lib:$LD_LIBRARY_PATH' >> ~/.bashrc
 source ~/.bashrc
 ```
 
 (5) Verify by running `rocminfo` command. If error message displayed instead of lots of gfx1200 info/etc., the `/dev/dxg` device may not have correct ownership permissions because of WSL: proceed to (5-b)
 
 (5-b) If (5) did not complete successfuly, create custom udev file rule:
 ```
 echo 'KERNEL=="dxg", MODE="0666", GROUP="render"' | sudo tee /etc/udev/rules.d/99-dxg.rules
 ```
 Then verify systemd is set as enabled in `/etc/wsl.conf`, so udev rules will execute on startup and modify ownership of device:
 ```
 [boot]
 systemd=true
 ```
 Then restart WSL (fully disconnect all terminals/IDEs, run `wsl --shutdown` in Powershell, then reconnect) and re-verify with `rocminfo`.


## Download + verify ollama ROCm interface
Download latest .ZST file and checksum direct from GitHub releases, verify with sha256. Modify release version number as needed.

```
curl -fsSL -O https://github.com/ollama/ollama/releases/download/v0.32.1/ollama-linux-amd64-rocm.tar.zst
curl -fsSL -O https://github.com/ollama/ollama/releases/download/v0.32.1/sha256sum.txt

sha256sum -c sha256sum.txt --ignore-missing
```

## Inspect + install ollama ROCm interface
As before.
```
tar -tf ollama-linux-amd64-rocm.tar.zst
sudo tar -xf ollama-linux-amd64-rocm.tar.zst -C /usr
```

## Run ollama
Start server locally:
```
ollama serve
```
then test in another terminal:
```
ollama -v
```
