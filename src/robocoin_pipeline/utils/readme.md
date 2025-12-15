
# 需求列表

## 必要结论

- **仅在下载时保证文件安全**

- **hardlink_mapping.json一定要存文件级的hardlink**

- **只有文件存在的时候关心版本号**

- **存储文件哈希值**

- **沿着hardlink链递归拉取，先取差集删除再增量拉取**

## 工具

文件hash？(hashlib md5)

## 方法说明

### memory_manage（tar_pull会调用）

前置要求：
tar_pull已将file_tar.json下载下来了

输入：

- dataset_name
- field_list
- episode_idx_list

算法：

1. 读取file_tar.json并计算所有要下载的tar先加入set(防止重复计算)，计算出所需空间，并计算现在还剩的空间
2. 若总空间（用户设定的本来就不够）不够，直接报错
3. 若总空间够，则尝试删除最老的dataset直到剩余空间够

注意：**pull和push都要更新dataset的timestamp**

输出：无

### tar_pull（代理数据的下载）

输入:

- dataset_name
- field_list
- episode_idx_list

算法：

1. 拉取file_tar.json
2. 空间检查
3. 拉取所需的tar，并解压
4. 删除不需要的文件

### tar_build

输入:

- dataset_name
- field_list
- episode_idx_list

假设文件结构是：

- meta
- data
- video

会自动将meta和data下的和video下的都打包

算法：
遍历上述的几个文件夹

1. 遍历文件夹中的在episode_idx_list有的文件
2. 按自增id创建tar包
3. 如果文件在hardlink_mapping.json中则跳过（防止重复上传，只保留原始文件）。否则向其中添加文件直到大小>=50MB，并将文件所在tar包信息写入json，并将tar包的大小写入json中
4. 直到所有episode_idx_list对应idx的文件都被添加完毕

### tar_push

输入:

- dataset_name
- field_list
- episode_idx_list

算法：

- 构建包，调用tar_build

### pull_files

输入:

- dataset_name
- field_list
- episode_idx_list

算法：
对于每个field

1. 拉取 hardlink_mappings
2. 先递归拉去要链接的field(依赖于有向无环图！！)
3. 将本地file_hash.json重命名成local_file_hash.json
4. 拉取file_hash.json
5. 与本地local_file_hash.json对比，删除差集
6. 拉取本地不存在的

输出：
原始文件

后续：
需要调用rebuild_hardlink

### rebuild_hardlink

需要：有完整的的dataset的flow分支

输入：

- hardlink_mappings.json
- 已经下载好的文件
- 需要update的文件list

算法：
~~1. 区分是文件夹还是文件
    1. 是文件则建立硬链接
    2. 若是文件夹则建立软链接~~

~~1. 安全创建文件硬链接~~

1. 直接覆盖原有硬链接

输出：

- 无（重建好的hardlink）

## 草稿

第一性：**同步nas和本地文件**

单位：
~~数据集-field~~
数据集-field-episode_idx
必要输入：

- dataset_name
- field_list
- episode_idx_list

方式：
~~增量更新-只更新有更改的feature？~~

增量更新-**优先保证同步**

只更改需要更改的？~~(hardlink怎么办？)~~
~~若hardlink_mappings.json有更改则重建hardlink?~~

### 涉及递归重建问题

- 重建需要删除已有的hardlink文件及其链接的文件
- 涉及增删改，需保证**文件安全** ~~先建立再重命名?~~
**仅在下载时保证文件安全！**

### 只要有更新必须删除所有hardlink**

~~*最好是只更新需要更新的*  如何找？
根据更新的field反向查找每个field下的hardlink_mappings.json，查看是否需要更新？
若只更新了单个episode？
**说明hardlink_mapping.json**~~尽量~~**一定要存文件级的hardlink**
根据hardlink_mapping.json即可反向查找所有需要修改hardlink的 *会不会有遗漏的野链接存在？*
什么时候会有：
文件更新(且hardlink_mapping.json未更新)时：文件更新->hardlink_mapping.json查询到hardlink文件，删除原hardlink并重建。 不会有问题！
**hardlink_mapping.json更新时：扫描一遍，删除在json中没有记录的文件！**~~

现在的问题是

如果可以拉取单个文件的话我的版本管理难做

难做在 配置文件也需要存储单个文件的hash值 难做吗？
还需要反向去建立各种hardlink 如何知道需要建立哪些hardlink
还需要删除无用的野hardlink

**问题出在上游更新！**

**最好是上游更新则下游也必须更新！
需要知道上下游关系，但现在缺失这个关系！**

此外更新的单位也有问题，不太可能只做文件级的更新吗？

最好像git一样只做仓库级的更新？

还是说其实不需要反向去传播，需要哪个更新哪个即可，只**需要保证field级的同步，而非dataset级的同步！**

是的，只需要保证单向的，不需要保证双向的。

~~**只要有更新必须重建所有hardlink**~~

~~**pull时不用关心push的事情，版本号是field的版本号**~~

~~**push也是只需要field的版本号**~~

~~**每次拉取都要先清除本地要拉的缓存**~~

沿着hardlink链递归拉取

怎么处理多余的文件？即在云端被删除的文件？
要删除文件哈希表与云端哈希表的差集的文件，再拉取剩余的

---
接下来是文件tar管道的问题

第一性：要求：nas上episode仅以tar包形式存储，video又有tar包又有源文件
，本地需要接收tar包后解压后删除tar包。tar包每个50-100M

问题：如何存储tar包和文件的关系？

使用file_tar.json存储，**存储每个文件存储在哪个tar包中**{[filename]:[tar_name]}

还需要让用户设置环境变量的脚本

---
关于存储管理：

设置环境变量设置自动存储管理的开启和关闭

一下讨论默认开启的情况

第一性：是为了让缓存的文件不超过用户设定的buffer大小

pull的时候要检查剩余的buffer大小和~~数据集大小~~将要下载的文件的总大小

如果不够，则尝试先将最老的dataset删除。

pull和push都要更新dataset下的update_time.json中的时间戳，这样才方便查找删除哪个

todo :

- raw_data的处理
- 添加episode_list 和 video_list
- 拉取hardlink源文件的时同样要做file_hash的检测，local_file_hash->file_hash->exist?->same_hash?
