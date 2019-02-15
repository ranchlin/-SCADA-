import sys
import os

sys.path.insert(99, './df_jf')
sys.path.insert(99, '../df_jf')
sys.path.insert(99, '/users/hdpsbp/felix/file_cache')

from core.config import *
import pandas as pd
from file_cache.utils.util_pandas import *
import matplotlib.pyplot as plot
from file_cache.cache import file_cache
import numpy as np
from functools import lru_cache
from munch import *
import json

from glob import glob

closed_ratio = 0.85

def get_predict_col():
    col_list = [col for col in list(date_type.keys()) if 'var' in col]
    return sorted(col_list)
#
# @file_cache()
# def get_input_analysis(gp_type='missing'):
#     df = pd.DataFrame()
#
#     for wtid in range(1, 34):
#         wtid = str(wtid)
#         train = pd.read_csv(f"./input/{wtid.rjust(3,'0')}/201807.csv")
#         logger.debug(f'================{wtid}================')
#         logger.debug(f'{train.shape}, {train.wtid.min()}, {train.wtid.max()}')
#         summary = {}
#         for col in train:
#             if gp_type == 'missing':
#                 summary[col] = int(pd.isna(train[col]).sum())
#             elif gp_type =='max':
#                 summary[col] = train[col].max()
#             elif gp_type == 'min':
#                 summary[col] = train[col].min()
#             elif gp_type == 'nunique':
#                 summary[col] = train[col].nunique()
#             else:
#                 raise Exception('Unknown gp_type:%s' % gp_type)
#
#         summary['wtid'] = wtid
#         summary['total'] =  len(train)
#         #logger.debug(summary)
#         df = df.append(summary, ignore_index=True)
#     return df

#
# def get_analysis_enum():
#     col_list = ['wtid','var053','var066','var016','var020','var047',  ]
#
#     train_list = []
#     for wtid in range(1, 34):
#         wtid = str(wtid)
#         train = pd.read_csv(f"./input/{wtid.rjust(3,'0')}/201807.csv", usecols=col_list)
#         train = train.groupby(col_list).agg({'wtid':'count'})
#         train.rename(index=str, columns={"wtid": "count"}, inplace=True)
#         train = train.reset_index()
#         #print(train.shape)
#         train_list.append(train)
#
#     all = pd.concat(train_list)
#     return all


@lru_cache()
@file_cache()
def get_sub_template():
    template = pd.read_csv('./input/template_submit_result.csv')
    template.ts = pd.to_datetime(template.ts)
    template = template.set_index(['ts', 'wtid'])

    for wtid in range(1, 34):
        wtid = str(wtid)
        train = pd.read_csv(f"./input/{wtid.rjust(3,'0')}/201807.csv")
        #train = pd.read_csv('./input/001/201807.csv')
        train['sn'] = train.index
        train = train.set_index(['ts', 'wtid'])
        train = train[train.index.isin(template.index)]
        template = template.combine_first(train)
        logger.debug(f'wtid={wtid}, {template.shape}, {train.shape},')
    template = template.reset_index()
    template = template.sort_values(['wtid', 'ts', ])
    return template


@timed(level='debug')
@lru_cache(maxsize=68)
def get_train_ex(wtid):
    wtid = str(wtid)
    train = pd.read_csv(f"./input/{wtid.rjust(3,'0')}/201807.csv", parse_dates=['ts'])
    old_shape = train.shape

    train.set_index('ts', inplace=True)

    template = get_sub_template()
    template = template[template.wtid == int(wtid)]
    template.set_index('ts', inplace=True)
    template = template.drop(columns='sn', errors='ignore')

    #logger.debug(f'template={template.shape}')

    train = train.combine_first(template)

    logger.debug(f'Convert train#{wtid} from {old_shape} to {train.shape}')

    train.reset_index(inplace=True)

    train.sort_values('ts', inplace=True)

    train.reset_index(inplace=True, drop=True)

    train['time_sn'] = (train.ts - pd.to_datetime('2018-07-01')).astype(int)   / 1000000000

    train['time_slot_3'] = (train.ts - pd.to_datetime('2018-07-01')).astype(int) // 3000000000
    train['time_slot_7'] = (train.ts - pd.to_datetime('2018-07-01')).astype(int) // 7000000000

    return train



@file_cache()
def get_missing_block_all():
    """
    wtid, col, begin, end
    :return:
    """
    df = pd.DataFrame(columns=['wtid', 'col', 'begin', 'end'])
    columns = list(date_type.keys())
    columns.remove('wtid')
    columns = sorted(columns)
    for wtid in sorted(range(1, 34), reverse=True):
        for col in columns:
            for begin, end in get_missing_block_for_col(wtid, col):
                df = df.append({'wtid':wtid, 'col':col,
                                'begin':begin, 'end':end
                                }, ignore_index=True)
    return df

@file_cache()
def get_data_block_all():
    missing = get_missing_block_all()
    df_list = []
    for wtid in range(1, 34):
        for col in missing.col.drop_duplicates():
            df_tmp = missing.loc[(missing.wtid == wtid) & (missing.col == col)]
            missing_end = df_tmp.end.max()
            df_tmp.sort_values('begin', inplace=True)
            df_tmp['begin'], df_tmp['end'] = (df_tmp.end.shift(1) + 1).fillna(0), df_tmp.begin - 1

            df_tmp['min'], df_tmp['max'], df_tmp['distinct'] = None, None, None

            train = get_train_ex(wtid)
            train_len = len(train)

            df_tmp = df_tmp.append({'wtid': wtid, 'col': col,
                                    'begin': missing_end + 1,
                                    'end': train_len - 1,
                                    }, ignore_index=True)

            for index, row in df_tmp.iterrows():
                df_tmp.loc[index, 'distinct'] = train.loc[row.begin:row.end, row.col].nunique()
                if 'float' in date_type[row.col].__name__:
                    df_tmp.loc[index, 'min'] = train.loc[row.begin:row.end, row.col].min()
                    df_tmp.loc[index, 'max'] = train.loc[row.begin:row.end, row.col].max()

            # df_tmp.length = df_tmp.end - df_tmp.begin

            df_list.append(df_tmp)
    return pd.concat(df_list)



@lru_cache()
def get_blocks():
    train = get_data_block_all()

    missing = get_missing_block_all()

    train['kind'] = 'train'
    missing['kind'] = 'missing'

    all = pd.concat([train, missing])

    all['length'] = all.end - all.begin +1
    all.sort_values(['wtid','col','begin'], inplace=True)

    all['data_type'] = all.col.apply(lambda val: date_type[val].__name__)
    return all.reset_index(drop=True)


def get_break_block():
    for wtid in range(1, 34):
        train = get_train_ex(wtid)
        train = train[date_type.keys()]

def get_missing_block_for_col(wtid, col):
    train = get_train_ex(wtid)
    missing_list = train[pd.isna(train[col])].index

    block_count = 0
    last_missing = 0
    block_list = []
    for missing in missing_list:
        if missing <= last_missing:
            continue

        block_count += 1
        begin, end = get_missing_block_single(wtid, col, missing)
        block_list.append((begin, end))

        last_missing = end


        msg =f'wtid={wtid:2},{col}#{block_count:2},length={1+end-begin:4},' \
                      f'begin={begin},' \
                      f'end={end},' \
                      f'missing={missing},'
        logger.debug(msg)
    logger.debug(f'get {block_count:2} blocks for wtid:{wtid:2}#{col}, type:{date_type[col]}')

    return block_list



def get_missing_block_single(wtid, col, cur_missing):
    train = get_train_ex(wtid)
    begin = train[col].loc[:cur_missing].dropna(how='any').index.max() + 1
    end   = train[col].loc[cur_missing:].dropna(how='any').index.min() - 1
    return begin, end


def get_train_df_by_val(train,val_feature, window, drop_threshold):
    #local_args = locals()
    try:
        window_ratio = window
        missing_length = len(val_feature)

        cur_windows = max(3, missing_length * window_ratio)
        cur_windows = int(cur_windows)

        val_begin = val_feature.index.min()
        val_end = val_feature.index.max()

        begin = max(val_begin - cur_windows, 0)
        end = val_end + cur_windows
        logger.debug(f'part#1:{begin},{val_begin}')
        logger.debug(f'part#2:{val_end+1},{end+1}')
        part1 = train.iloc[begin : val_begin]
        part2 = train.iloc[val_end+1 : end+1]

        train_feature = pd.concat([part1, part2])
        #TODO, drop columns by threshold
        #train_feature = train_feature.dropna(how='any')

        for col in train_feature.columns[1:]:
            valid_count_train = pd.notnull(train_feature[col]).sum()
            valid_count_val = pd.notnull(val_feature[col]).sum()
            coverage_train = round(valid_count_train/len(train_feature), 4)
            coverage_val = round(valid_count_val / len(val_feature), 4)
            if  coverage_train < drop_threshold or coverage_val < drop_threshold:
                del train_feature[col]
                del val_feature[col]
                logger.info(f'Remove {col}, coverage train/val is:{coverage_train}/{coverage_val} less than {drop_threshold}')
            else:
                train_feature[col].fillna(method='ffill', inplace=True)
                val_feature[col].fillna(method='ffill', inplace=True)

                train_feature[col].fillna(method='bfill', inplace=True)
                val_feature[col].fillna(method='bfill', inplace=True)


        if pd.isna(train_feature.iloc[:,1:]).any().any() :
            #logger.error(f'Train has none for {local_args}')
            raise Exception(f'Train {train_feature.shape} has none for {train_feature.index.min()}')

        if pd.isna(val_feature.iloc[:,1:]).any().any():
            #logger.error(f'Val has none for {local_args}')
            raise Exception(f'Val {val_feature.shape} has none for {local_args.index.min()}')

        time_gap = max(30, val_feature.time_sn.max() - val_feature.time_sn.min())
        time_begin = val_feature.time_sn.min() - 5 * time_gap
        time_end = val_feature.time_sn.max() + 5 * time_gap
        # Make the train closed to validate
        train_feature = train_feature[(train_feature.time_sn >= time_begin) & (train_feature.time_sn <= time_end)]
        logger.debug(f'train_t_sn:{train_feature.time_sn.min()}, {train_feature.time_sn.min()},'
                     f' val_time_sn:{val_feature.time_sn.min()}:{val_feature.time_sn.max()}')
        logger.debug(f'Range: Train_val: '
                     f'[{part1.index.min()}, {part1.index.max()} ]({len(part1)}) '
                     f'[{val_feature.index.min()}, {val_feature.index.max()}]({len(val_feature)}), '
                     f'[{part2.index.min()}, {part2.index.max()} ]({len(part2)}), cur_windows:{cur_windows}' )


    except Exception  as e:
        #logger.error(val_feature)
        logger.exception(e)
        logger.exception(f'Can not get train for val block:{val_begin}:{val_end}')
        raise e
    if len(train_feature) == 0:
        logger.exception(f'Train feature length is none, for val block:{val_begin}:{val_end}, window:{window}')
        raise Exception(f'Train feature length is none, for val block:{val_begin}:{val_end}, window:{window}')
    return train_feature



@lru_cache()
@file_cache()
def get_std_all():
    df = pd.DataFrame(columns=['wtid', 'col', 'mean', 'min', 'max', 'std'])
    columns = list(date_type.keys())
    columns.remove('wtid')
    columns = sorted(columns)
    for wtid in sorted(range(1, 34), reverse=True):
        for col in columns:
            std_sample =  check_std(wtid,col)
            df = df.append(std_sample,ignore_index=True)

    df['data_type'] = df.col.apply(lambda val: date_type[val].__name__)
    return df

def check_std(wtid, col, windows=100):
    std_list = []
    block = get_blocks()

    train_block = block.loc[(block.wtid == wtid) & (block.col == col) & (block.kind == 'train')]

    missing_block = block.loc[(block.wtid == wtid) & (block.col == col) & (block.kind == 'missing')]

    for missing in [missing_block['length'].sort_values().max()]:
        cur_windows = max(windows, missing)
        at_least_len = missing + 2 * cur_windows
        logger.debug(
            f'at_least_len={at_least_len}, window={cur_windows}, missing_len={missing} {train_block[train_block["length"]>=at_least_len].shape}')
        for index, cur_block in (train_block[train_block['length'] >= at_least_len]).iterrows():
            train = get_train_ex(wtid)
            begin, end = cur_block.begin, cur_block.end
            # Get the data without missing
            block = train.iloc[begin:end + 1][['time_sn', col]]

            block = block.reset_index(drop=True)

            # only pick the latest data closed to training
            block = block.iloc[-at_least_len:]

            std_list.append(round(block[col].std(),3))


    std_list = np.array(std_list)
    summary_map = {
        'wtid':wtid, 'col':col,
        'mean':round(std_list.mean(),3),
        'min':std_list.min(),
        'max':std_list.max(),
        'std':round(std_list.std(), 3),
    }
    logger.debug( f'Summary: {summary_map}')


    return summary_map


def convert_enum(df):
    for col in df:
        if col in date_type and 'int' in date_type[col].__name__:
            df[col] = df[col].astype(int)
    return df

#
# @timed()
# def group_columns(wtid=1):
#     col_list = get_blocks().col.drop_duplicates()
#     existing = []
#     gp_list = []
#     for col in col_list:
#         if col in existing:
#             continue
#         gp = get_closed_columns(col, wtid)
#         gp = list(gp.values)
#         existing.extend(gp)
#         gp_list.append(gp)
#     return sorted(gp_list, key=lambda val: len(val), reverse=True )


@timed()
@lru_cache(maxsize=9999999)
def get_closed_columns(col_name, wtid=1, threshold=closed_ratio):
    sub = get_train_ex(wtid)

    sub = sub.dropna(how='any')

    cor = np.corrcoef(sub.drop(axis='column', columns=['ts', 'wtid']).T)

    col_list = sub.columns[2:]

    #print(cor.shape, sub.shape)

    cor = pd.DataFrame(index=col_list, columns=col_list, data=cor)[col_name]

    return cor.loc[cor >= threshold].sort_values(ascending=False).index


@timed()
@file_cache()
def get_pure_block_list(kind='data'):
    df = pd.DataFrame()
    for wtid in range(1, 34):
        train = get_train_ex(wtid)
        #print(train.shape)
        if kind == 'data':
            train = train.dropna(how='any')
        else:
            col_list = list(date_type.keys())
            col_list.remove('wtid')
            train = train[col_list]
            train = train[train.sum(axis=1) == 0]
        train['old_index'] = train.index
        train = train[['old_index']]
        train['shift_index'] = train.old_index.shift(1)

        train['jump'] = train.apply(lambda row: row.old_index - 1 == row.shift_index, axis=1)

        block_begin = train[train.jump == False]
        for begin, end_ex in zip(block_begin.old_index, block_begin.old_index.shift(-1)):
            end = train.loc[:end_ex - 1].index.max()
            df = df.append({
                'wtid':int(wtid),
                'begin':begin,
                'end':end,
                'length':end-begin+1,
                 }, ignore_index=True)
    df.wtid = df.wtid.astype(int)

    return df

#
# @lru_cache()
# @file_cache()
# def adjust_block(ratio=0.8):
#     block = get_blocks()
#     block['begin_ex'] = block.begin
#     block['end_ex'] = block.end
#
#     data_block = get_pure_block_list(kind='data')
#
#     wtid_list = range(1, 5)
#     for wtid in wtid_list:
#         for index, row in data_block.loc[data_block.wtid == wtid].iterrows():
#             end = row.end
#             length = row.length
#             # logger.info(f"block.loc[(block.begin >= end) & (block.wtid==wtid) , 'begin_ex']={block.loc[(block.begin >= end) & (block.wtid==wtid) , 'begin_ex'].shape}")
#             block.loc[(block.begin >= end) & (block.wtid == wtid), 'begin_ex'] = block.loc[(block.begin >= end) & (
#             block.wtid == wtid), 'begin_ex'] - ratio * length
#             block.loc[(block.begin >= end) & (block.wtid == wtid), 'end_ex'] = block.loc[(block.begin >= end) & (
#             block.wtid == wtid), 'end_ex'] - ratio * length
#     return block.loc[block.wtid.isin(wtid_list)]


def rename_col_for_merge_across_wtid(wtid, col_name, related_col_count):
    col_list = [col_name, 'time_sn', 'time_slot_7']
    if related_col_count > 0:
        closed_col = get_closed_columns(col_name, wtid, closed_ratio) #rename_col_for_merge_across_wtid
        if len(closed_col) >1:
            closed_col = closed_col[1:related_col_count+1]
            col_list.extend(closed_col)

    train = get_train_ex(wtid)[col_list]
    train.columns = [f'{col}_{wtid}' if 'var' in col else col for col in train.columns]
    return train


@lru_cache()
@file_cache()
def get_corr_wtid(col_name):
    train = rename_col_for_merge_across_wtid(1, col_name, 0) #get_corr_wtid

    for wtid in range(2, 34):
        train_tmp = rename_col_for_merge_across_wtid(wtid, col_name, 0) #get_corr_wtid
        train = train.merge(train_tmp, on=['time_slot_7'])
        train = train.drop_duplicates('time_slot_7')
        logger.debug(f'col#{col_name}, the shpae after wtid:{wtid} is:{train.shape}')
    train = train.set_index('time_slot_7')

    train = train.dropna(how='any')

    cor = train[[col for col in train.columns if 'var' in col]]
    col_list = cor.columns

    logger.debug(col_list)
    cor = np.corrcoef(cor.T)

    # print(train.shape)
    #
    # print(train.shape, train.index.min(), train.index.max())
    #
    # print(col_list)
    cor = pd.DataFrame(index=col_list, columns=col_list, data=cor)
    logger.debug(cor.where(cor < 0.99).max().to_frame().T)

    logger.debug(cor.where(cor < 0.99).idxmax().to_frame().T)

    return cor

@timed()
@lru_cache(maxsize=256)
def get_train_feature_multi_file(wtid, col, file_num, related_col_count):
    local_args = locals()
    file_num = int(file_num)
    if file_num <1:
        raise Exception(f'file_num should be large then 1, cur file_num is {file_num}, {local_args}')

    cor = get_corr_wtid(col)
    related_wtid_list = cor[f'{col}_{wtid}'].sort_values(ascending=False)[1:file_num]
    logger.info(f'The top#{file_num} files for wtid:{wtid}, col:{col} is '
                f'{dict(zip(related_wtid_list.index,np.round(related_wtid_list.values,3)))}')
    related_wtid_list = [int(col.split('_')[1]) for col in related_wtid_list.index]

    #Find data for original Wtid
    train = rename_col_for_merge_across_wtid(wtid, col, related_col_count) #get_train_feature_multi_file

    input_len = len(train)
    #Rename back
    train = train.rename(columns={f'{col}_{wtid}':col})
    train['id']=train.index

    #Join the feature from other wtid
    for related_wtid in related_wtid_list:
        #TODO
        train_tmp = rename_col_for_merge_across_wtid(related_wtid, col, 0) #get_train_feature_multi_file
        train_tmp = train_tmp.drop(axis='column', columns=['time_sn'])
        train = train.merge(train_tmp, how='left', on=['time_slot_7'])
        train = train.drop_duplicates(['id'])
    train = train.set_index('id')
    col_list = [col for col in train.columns if 'var' in col]
    col_list.append('time_sn')
    train = train[col_list]
    #TODO replace with threshold
    #train.iloc[:, 1:] = train.iloc[:,1:].fillna(method='ffill')

    if len(train) != input_len:
        logger.exception(f"There are some row are missing for wtid:{wtid}, col:{col}, file_num:{file_num}")
        raise Exception(f"There are some row are missing for wtid:{wtid}, col:{col}, file_num:{file_num}")

    return train.sort_index()


@timed()
def get_train_val(miss_block_id, file_num, window, related_col_count,drop_threshold, shift, after):
    local_args = locals()
    logger.info(f'input get_train_val:{locals()}')
    blks = get_blocks()
    cur_blk = blks.iloc[miss_block_id]
    blk_id, b1, e1, b2, e2, b3, e3 = get_train_val_range(miss_block_id, window, shift, after)
    train = get_train_feature_multi_file(cur_blk.wtid, cur_blk.col, file_num, related_col_count)


    val_df = train.loc[b2:e2]
    train_df = get_train_df_by_val(train, val_df, window, drop_threshold)

    remove_list, keep_list = get_col_need_remove(miss_block_id)
    if len(remove_list) > 0:
        val_df.drop(axis='column', columns=remove_list, errors='ignore')
        train_df.drop(axis='column', columns=remove_list, errors='ignore')
        logger.info(f'Remove col:{remove_list}, keep:{keep_list} for blk_id:{miss_block_id}')

    if train_df is None or  len(train_df) ==0 :
        logger.error(f'No train is get for :{local_args}')
        raise Exception(f'No train is get for :{local_args}')

    return train_df ,val_df, blk_id


@timed()
def get_train_val_range(miss_block_id, window, shift, after=True):
    blks = get_blocks()
    missing_block = blks.iloc[miss_block_id]

    blk, blk_id = get_closed_block(miss_block_id, window, shift, after)

    missing = int(missing_block.length)
    shift_adj = int(shift * (window + 1) * missing)

    part_1_b = int(blk.begin + shift_adj)
    part_1_e = int(part_1_b + np.ceil(window * missing) - 1)

    val_b, val_e = part_1_e + 1, int(part_1_e + missing)
    part_2_b, part_2_e = val_e + 1, int(val_e + np.ceil(window * missing))

    logger.info(f'range: {part_1_b}:{part_1_e}, {val_b}:{val_e}, {part_2_b}:{part_2_e} for {DefaultMunch(None,blk)}')
    return blk_id, int(part_1_b), int(part_1_e), int(val_b), int(val_e), int(part_2_b), int(part_2_e)


@timed()
def get_closed_block(miss_block_id, window, shift, after=True):
    local_args = locals()
    blks = get_blocks()
    missing_block = blks.iloc[miss_block_id]

    if missing_block.kind == 'train':
        raise Exception(f'The input block should be missing:{missing_block}')
    miss_len = int(missing_block.length)
    window_len = np.ceil((2 * window + 1) * miss_len \
                         + shift * (window + 1) * miss_len) + 5  # Buffer for round

    bk = get_blocks()
    max_data_len = bk.loc[(bk.col == missing_block.col)
                    & (bk.kind == 'train')
                    & (bk.wtid == missing_block.wtid)].length.max()

    if window_len > max_data_len:
        logger.warning(f'Expect block have {window_len} length, but max is {max_data_len}, args:{local_args}')
        window_len = max_data_len


    closed = bk.loc[(bk.col == missing_block.col)
                    & (bk.kind == 'train')
                    & (bk.wtid == missing_block.wtid)
                    & (bk.length >= window_len)
                    ]



    if after:
        tmp = closed.loc[closed.begin > missing_block.begin]
        # Closed After
        if len(tmp) > 0:
            return tmp.iloc[0], tmp.index[0]
    else:
        # Closed Before
        tmp = closed.loc[closed.begin < missing_block.begin]
        if len(tmp) > 0:
            return tmp.iloc[-1], tmp.index[-1]

    if len(tmp) == 0:
        if after:
            tmp = closed.loc[closed.begin < missing_block.begin]
            if len(tmp) > 0:
                return tmp.iloc[-1], tmp.index[-1]
        else:
            tmp = closed.loc[closed.begin > missing_block.begin]
            if len(tmp) > 0:
                return tmp.iloc[0], tmp.index[0]
    logger.error(f"No closed block {window_len} if found for:{local_args}")
    raise Exception(f"No closed block {window_len} if found for:{local_args}")


def get_bin_id_list(gp_name):
    file = f'./score/{gp_name}/*'
    bin_list =  [int(file.split('/')[-1]) for file in sorted(glob(file))]
    return sorted(bin_list)

@file_cache()
def get_closed_col_ratio_df():
    blk_list = get_blocks()
    blk_list = blk_list.loc[blk_list.kind=='missing']#[:200]
    blk_list
    df = pd.DataFrame()
    for blk_id, blk in blk_list.iterrows():
        col_list  = get_closed_columns(blk.col, wtid=1, threshold=closed_ratio) #get_closed_col_ratio_df
        tmp_blk = blk_list[(blk_list.wtid==blk.wtid)  &
                     (blk_list.kind=='missing')&
                     (blk_list.col.isin(col_list) ) &
                      (blk_list.begin == blk.begin) & (blk_list.end == blk.end)]

        #print(len(tmp_blk),len(col_list) )

        if len(tmp_blk) == len(col_list):
            continue

        train= get_train_ex(blk.wtid)

        tmp = train.loc[blk.begin:blk.end, col_list]
        sr_map = {}
        sr_map['blk_id']=blk_id
        sr_map['col_name']=blk.col
        sr_map['wtid'] = blk.wtid
        sr_map['begin'] = blk.begin
        sr_map['end'] = blk.end
        sr_map['length'] = blk.length
        for sn, col in enumerate(col_list):
            ratio =  pd.notna(tmp[col]).sum() /len(tmp)
            sr_map[f'name_{sn}']=col
            sr_map[f'val_{sn}']= ratio
        df = df.append(sr_map,ignore_index=True)
        #print(df.shape, df.val_2.sum())
    return df


@timed()
def get_col_need_remove(blk_id, closed_ratio=closed_ratio):
    """
    Check if introduce the related column, how many NONE col need to remove
    :param blk_id:
    :param closed_ratio:
    :return:
    """
    bk = get_blocks()

    miss = get_closed_col_ratio_df()
    miss = miss.set_index('blk_id')
    cur_name = bk.ix[blk_id, 'col']

    closed_col = get_closed_columns(cur_name, wtid=1, threshold=closed_ratio)
    closed_col = list(closed_col)
    closed_col.remove(cur_name)

    keep_list = []
    if blk_id not in miss.index:
        return closed_col, keep_list


    for i in range(1, 6):
        threshold = float(miss.ix[blk_id, f'val_{i}'])
        if threshold > 0:
            col_name = miss.ix[blk_id, f'name_{i}']
            # The column will keep
            closed_col.remove(col_name)
            keep_list.append(col_name)
    return closed_col, keep_list


if __name__ == '__main__':
    get_closed_col_ratio_df()




